# VoxQuill - Voice-to-text input for AI prompting
# Copyright (C) 2026 Lancelot MEI
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
import os
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMessageBox
from core.audio import AudioProvider
from core.asr import ASRWorker
from core.asr_config import ensure_model_ready, load_asr_config, set_active_model
from core.ipc import IPCServer
from core.logging_utils import log
from ui.main_window import AIInputBox
from ui.style import load_app_stylesheet
from ui.tray import SystemTrayIcon
from core.path_utils import get_resource_path

# Wayland positioning bypass: Requires libxcb-cursor0.
# Without this, GNOME Wayland forbids absolute move() and WindowStaysOnTop.
if sys.platform == "linux" and "WAYLAND_DISPLAY" in os.environ:
    # Safe check for the required library to avoid "core dumped" crash.
    import glob
    if glob.glob("/usr/lib/**/libxcb-cursor.so.0", recursive=True):
        os.environ["QT_QPA_PLATFORM"] = "xcb"

class SignalBridge(QObject):
    partial_result = pyqtSignal(str)
    final_result = pyqtSignal(str)
    finished = pyqtSignal() # New signal
    ipc_command = pyqtSignal(str)

def main():
    # If using Wayland natively, some GNOME versions allow move() 
    # if the window type is ToolTip.
    # Fix HiDPI scaling for XWayland
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(get_resource_path("resource/main_small_color.png")))
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(load_app_stylesheet())
    
    bridge = SignalBridge()
    
    # 1. Initialize Core
    audio = AudioProvider()
    asr = None
    
    # 2. Initialize UI
    window = AIInputBox()
    
    # 3. Initialize IPC
    ipc = IPCServer(command_handler=lambda c: bridge.ipc_command.emit(c))
    
    # 4. Define Helper Functions
    def create_asr_worker(model_id):
        return ASRWorker(
            audio,
            on_partial_result=lambda t: bridge.partial_result.emit(t),
            on_final_result=lambda t: bridge.final_result.emit(t),
            on_finished=lambda: bridge.finished.emit(),
            model_id=model_id,
        )

    def ensure_selected_model_ready():
        model_id = window.selected_model_id()
        if not model_id:
            QMessageBox.information(
                window,
                "No Model Installed",
                "No ASR model is installed. Open the Models page and download one first.",
            )
            return None
        try:
            set_active_model(model_id)
            model_config = load_asr_config(model_id=model_id)
            downloaded = ensure_model_ready(model_config)
            if downloaded:
                log(f"Main: Downloaded missing files for model '{model_id}'")
            return model_id
        except Exception as e:
            QMessageBox.critical(window, "Model Error", str(e))
            log(f"Main: Failed to prepare model '{model_id}': {e}")
            return None

    def ensure_asr_worker(model_id):
        nonlocal asr
        if asr is not None:
            current_model_id = asr.model_config["id"]
            if current_model_id == model_id:
                return True
            asr.stop()
            if asr.is_alive():
                asr.join(timeout=1.0)
            asr = None

        asr = create_asr_worker(model_id)
        asr.start()
        asr.set_paused(True)
        return True

    def start_recording():
        if window.is_recording: return
        log(f"Main: Start Triggered. Current state: recording={window.is_recording}")
        try:
            model_id = ensure_selected_model_ready()
            if not model_id:
                return
            ensure_asr_worker(model_id)
            if not audio.start():
                log("Main: Audio start failed; recording not started.")
                return
            asr.set_paused(False)
            window.set_recording_state(True)
            tray.set_recording_state(True)
            window.bring_to_front()
        except Exception as e:
            log(f"Main: Error during start_recording: {e}")

    def stop_recording():
        if not window.is_recording: return
        log(f"Main: Stop Triggered. Current state: recording={window.is_recording}")
        try:
            audio.stop() 
            asr.set_paused(True)
            window.set_recording_state(False)
            tray.set_recording_state(False)
        except Exception as e:
            log(f"Main: Error during stop_recording: {e}")

    def toggle_recording():
        if window.is_recording:
            stop_recording()
        else:
            start_recording()

    def quit_app():
        log("Main: Quitting Application")
        if asr:
            asr.stop()
        ipc.stop()
        audio.stop()
        app.quit()

    # 5. Connect Signals
    bridge.partial_result.connect(lambda t: window.update_text(t, is_final=False))
    bridge.final_result.connect(lambda t: window.update_text(t, is_final=True))
    bridge.finished.connect(window.on_engine_finished) # Connect to UI handler

    window.request_stop_and_copy.connect(stop_recording)

    def handle_ipc(command):
        if command == "toggle": toggle_recording()
        elif command == "show": 
            window.bring_to_front()
        elif command == "hide": window.hide()

    bridge.ipc_command.connect(handle_ipc)
    window.toggle_button.clicked.connect(toggle_recording)
    # window.clear_button.clicked.connect(window.clear_text) # Removed

    tray = SystemTrayIcon(window, start_recording, stop_recording, quit_app)
    tray.set_recording_state(False) # Initial state
    tray.show()

    ipc.start()

    
    window.show()
    
    try:
        sys.exit(app.exec())
    finally:
        if asr and asr.is_alive(): asr.join(timeout=1.0)
        if ipc.is_alive(): ipc.join(timeout=1.0)

if __name__ == "__main__":
    main()
