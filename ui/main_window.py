import os
import json
import re
import time
import subprocess
import pyperclip
try:
    import evdev
    from evdev import UInput, ecodes
except ImportError:
    evdev = None
from pynput.keyboard import Controller, Key
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QApplication, QMenu
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject, QTimer, QSize, QEvent
from PyQt6.QtGui import QShortcut, QKeySequence, QTextCursor, QCursor, QIcon
from core.asr_config import list_available_models, load_asr_config, get_history_dir, get_history_enabled
from core.logging_utils import log
from ui.style import apply_surface_shadow
from ui.model_manager import ModelManagerDialog
from core.path_utils import get_resource_path, get_config_path
from datetime import datetime

class AIInputBox(QMainWindow):
    request_stop_and_copy = pyqtSignal()

    def __init__(self):
        super().__init__()
        # Ensure it stays on top and is tool-like
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.is_recording = False
        self.committed_text = ""
        self._asr_updating = False
        self._pending_close = False 
        self._prompts = {}
        self._models = []
        self._resize_margin = 4
        self.keyboard = Controller()
        
        self._load_prompts()
        self._load_models()
        
        self.setWindowIcon(QIcon(get_resource_path("resource/main_small_color.png")))
        
        # Pre-generate icons
        self.idle_icon = QIcon(get_resource_path("resource/main_small_color_blue_256.png"))
        self.recording_icon = QIcon(get_resource_path("resource/main_small_color_256.png"))
        
        self._setup_ui()
        self._setup_shortcuts()
        self.center_on_screen()

    def center_on_screen(self):
        screen = QApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry() # This accounts for taskbars
        
        width = max(560, geometry.width() // 2)
        height = 100
        
        # Position horizontally center
        x = geometry.x() + (geometry.width() - width) // 2
        
        # Calculate the bottom 1/5 (20%) area of the screen
        bottom_area_start_y = geometry.y() + (geometry.height() * 4 // 5)
        bottom_area_height = geometry.height() // 5
        
        # Center the window vertically WITHIN that bottom area
        y = bottom_area_start_y + (bottom_area_height - height) // 2
        
        # Final safety bounds
        y = max(geometry.y(), min(y, geometry.y() + geometry.height() - height - 10))

        self.resize(width, height)
        self.move(x, y)
        log(f"UI: Positioned window at {x}, {y} with size {width}x{height}")

    def bring_to_front(self):
        self.show()
        # On Linux, some WMs ignore activateWindow, so we try multiple tricks
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()
        # Force set focus to text edit
        self.text_edit.setFocus()
        QTimer.singleShot(50, lambda: self.activateWindow())

    def _load_prompts(self):
        config_path = get_config_path("prompts.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self._prompts = json.load(f)
            except Exception as e:
                log(f"UI: Error loading prompts: {e}")

    def _load_models(self):
        try:
            self._models = list_available_models()
            self._active_model_id = load_asr_config()["id"]
        except Exception as e:
            log(f"UI: Error loading ASR models: {e}")
            self._models = []
            self._active_model_id = None

    def _setup_ui(self):
        self.central_widget = QWidget()
        self.central_widget.setObjectName("WindowRoot")
        self.setCentralWidget(self.central_widget)

        root_layout = QVBoxLayout(self.central_widget)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(0)

        self.surface = QWidget()
        self.surface.setObjectName("SurfaceFrame")
        root_layout.addWidget(self.surface)
        apply_surface_shadow(self.surface, blur_radius=20, y_offset=4)

        # Main layout with margins for border
        # We increase margins to 10px to separate buttons from resizing edges
        main_layout = QVBoxLayout(self.surface)
        main_layout.setContentsMargins(10, 4, 10, 4)
        main_layout.setSpacing(4)
        
        # 1. Header Row
        self.header_bar = QWidget()
        self.header_bar.setObjectName("HeaderBar")
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 2, 4, 2)
        header_layout.setSpacing(2)
        self.header_bar.setLayout(header_layout)
        
        self.model_button = QPushButton()
        self.model_button.setObjectName("ModelButton")
        self.model_button.setToolTip("Open model manager")
        self.model_button.clicked.connect(self._open_model_manager)
        header_layout.addWidget(self.model_button)
        
        header_layout.addSpacing(4)

        # Direct shortcuts for top 9 commands
        top_commands = list(self._prompts.items())[:9]
        for p_id, p_data in top_commands:
            btn = QPushButton(p_data["label"])
            btn.setObjectName("CommandButton")
            btn.setToolTip(f"Command: {p_data['command']}")
            btn.clicked.connect(lambda checked, text=p_data["text"]: self._insert_prompt(text))
            header_layout.addWidget(btn)
        
        # Unified menu for additional commands
        if len(self._prompts) > 9:
            self.more_button = QPushButton("More")
            self.more_button.setObjectName("MoreButton")
            
            self.menu = QMenu(self)
            for p_id, p_data in list(self._prompts.items())[9:]:
                action = self.menu.addAction(p_data["label"])
                action.setToolTip(f"Command: {p_data['command']}")
                action.triggered.connect(lambda checked, text=p_data["text"]: self._insert_prompt(text))
            
            self.more_button.setMenu(self.menu)
            header_layout.addWidget(self.more_button)
        
        header_layout.addStretch()
        
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("CloseButton")
        self.close_button.setFixedSize(26, 26)
        self.close_button.clicked.connect(self.hide)
        header_layout.addWidget(self.close_button)
        
        main_layout.addWidget(self.header_bar)
        
        self.input_container = QWidget()
        self.input_container.setObjectName("InputContainer")
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(8, 1, 8, 1)
        input_layout.setSpacing(8)

        self.text_edit = QTextEdit()
        self.text_edit.setMinimumHeight(42)
        self.text_edit.setPlaceholderText("Start speaking or type //...")
        self.text_edit.textChanged.connect(self._on_text_changed)
        input_layout.addWidget(self.text_edit, 1)

        self.toggle_button = QPushButton()
        self.toggle_button.setObjectName("RecordButton")
        self.toggle_button.setFixedSize(42, 42)
        self.toggle_button.setIconSize(QSize(42, 42))
        self.toggle_button.setIcon(self.idle_icon)
        self.toggle_button.setProperty("recording", False)
        input_layout.addWidget(self.toggle_button, 0, Qt.AlignmentFlag.AlignVCenter)

        main_layout.addWidget(self.input_container)
        
        self.setMouseTracking(True)
        self.central_widget.setMouseTracking(True)
        self.surface.setMouseTracking(True)
        self.header_bar.installEventFilter(self)
        self.model_button.installEventFilter(self)
        self.close_button.installEventFilter(self)
        if hasattr(self, "more_button"):
            self.more_button.installEventFilter(self)
        self.central_widget.installEventFilter(self)
        self.surface.installEventFilter(self)
        self.refresh_model_selector()

    def _setup_shortcuts(self):
        self.esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.esc_shortcut.activated.connect(self._on_esc_pressed)

    def _on_esc_pressed(self):
        if self.is_recording:
            self._pending_close = True
            self.request_stop_and_copy.emit()
        else:
            self.finish_and_copy()

    def _save_to_history(self, text):
        if not get_history_enabled():
            return
            
        try:
            history_dir = get_history_dir()
            if not os.path.exists(history_dir):
                os.makedirs(history_dir, exist_ok=True)
            
            now = datetime.now()
            # 1. Month-based filename: 2026-03vox.md
            filename = f"{now.strftime('%Y-%m')}vox.md"
            filepath = os.path.join(history_dir, filename)
            
            # 2. Date-based heading: #### 2026-03-30
            today_heading = f"#### {now.strftime('%Y-%m-%d')}"
            
            # Check if we need to add the heading
            add_heading = True
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    if today_heading in content:
                        add_heading = False
            
            with open(filepath, "a", encoding="utf-8") as f:
                if add_heading:
                    f.write(f"\n{today_heading}\n")
                
                # 3. New Format: ISO (No seconds) on its own line, no prefix for text
                timestamp = now.isoformat(timespec='minutes')
                f.write(f"\n{timestamp}\n{text}\n")
                
            log(f"UI: Saved to history: {filepath}")
        except Exception as e:
            log(f"UI: Error saving to history: {e}")

    def on_engine_finished(self):
        if self._pending_close:
            QTimer.singleShot(100, self.finish_and_copy)

    def finish_and_copy(self):
        text = self.text_edit.toPlainText().strip()
        
        # Yield focus without hiding the window.
        # We clear local focus, deactivate the window state, and lower it.
        # On many WMS, this will allow the previous window to regain focus 
        # while keeping this window visible (since it has StaysOnTop flag).
        self.text_edit.clearFocus()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowActive)
        self.lower()
        
        if text:
            QApplication.clipboard().setText(text)
            try: pyperclip.copy(text)
            except: pass
            
            # Simulate paste into the window that regained focus
            QTimer.singleShot(250, lambda: self._simulate_paste())
            self._save_to_history(text)
            
        self.clear_text()
        self._pending_close = False

    def _simulate_paste(self):
        # Use Wayland-aware tools to bypass XWayland input isolation
        is_wayland = "WAYLAND_DISPLAY" in os.environ
        if is_wayland:
            # 1. Try wtype (Compositor protocol - works on Sway/KDE, denied on GNOME)
            try:
                subprocess.run(["wtype", "-M", "ctrl", "v", "-m", "ctrl"], check=True)
                log("UI: Paste simulated via wtype (Wayland)")
                return
            except Exception as e:
                log(f"UI: wtype failed: {e}")

            # 2. Try evdev (Kernel level - robust fallback for GNOME if permissions allow)
            if evdev:
                try:
                    # Define the keys we intend to use
                    cap = {
                        ecodes.EV_KEY: [ecodes.KEY_LEFTCTRL, ecodes.KEY_V]
                    }
                    with UInput(cap, name="VoxQuill-Virtual-KB") as ui:
                        # Wait a tiny bit for the OS to register the new device
                        time.sleep(0.005) 
                        # Press Ctrl
                        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
                        # Press and release V
                        ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
                        # Release Ctrl
                        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
                        ui.syn()
                        log("UI: Paste simulated via evdev (Wayland/uinput)")
                        return
                except Exception as e:
                    log(f"UI: evdev failed: {e}")
            else:
                log("UI: evdev not available")

        # Fallback to pynput (X11 only)
        try:
            with self.keyboard.pressed(Key.ctrl):
                self.keyboard.press('v')
                self.keyboard.release('v')
            log("UI: Paste simulated via pynput (X11)")
        except Exception as e:
            log(f"UI: Paste failed: {e}")

    def set_recording_state(self, is_recording):
        self.is_recording = is_recording
        self.model_button.setEnabled(not is_recording)
        self.toggle_button.setProperty("recording", is_recording)
        self.toggle_button.setIcon(self.recording_icon if is_recording else self.idle_icon)
        self.toggle_button.style().unpolish(self.toggle_button)
        self.toggle_button.style().polish(self.toggle_button)

    def selected_model_id(self):
        return self._active_model_id

    def refresh_model_selector(self):
        self._load_models()
        active_name = "No model"
        for model in self._models:
            if model["id"] == self._active_model_id:
                active_name = model["display_name"]
                break
        self.model_button.setText(f"{active_name}  >")
        self.model_button.setEnabled(not self.is_recording)

    def _open_model_manager(self):
        dialog = ModelManagerDialog(self)
        dialog.models_changed.connect(self.refresh_model_selector)
        dialog.center_on_current_screen()
        dialog.exec()

    def _insert_prompt(self, p_text):
        cursor = self.text_edit.textCursor()
        cursor.insertText(p_text)
        self.text_edit.setFocus()

    def _on_text_changed(self):
        if self._asr_updating: return
        text = self.text_edit.toPlainText()
        self.committed_text = text
        for p_id, p_data in self._prompts.items():
            cmd = p_data["command"]
            if text.endswith(f"{cmd} "):
                self._asr_updating = True
                new_text = text[:-len(cmd)-1] + p_data["text"]
                self.text_edit.setPlainText(new_text)
                cursor = self.text_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.text_edit.setTextCursor(cursor)
                self.committed_text = new_text
                self._asr_updating = False
                break

    def eventFilter(self, obj, event):
        # Ensure cursor is updated for ALL tracked components to avoid "stuck" resize arrows
        if event.type() == QEvent.Type.MouseMove:
            self._update_resize_cursor(obj, event)

        if obj in (self.central_widget, self.surface):
            if event.type() == QEvent.Type.Leave:
                self.unsetCursor()
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    if self._start_window_resize(obj, event):
                        return True
        
        if obj is self.header_bar:
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._start_window_drag(event)
                    return True
            if event.type() == QEvent.Type.MouseButtonDblClick:
                return True
                
        return super().eventFilter(obj, event)

    def _start_window_drag(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def _edge_at_pos(self, obj, event):
        pos = event.position().toPoint()
        global_pos = obj.mapToGlobal(pos)
        local_pos = self.mapFromGlobal(global_pos)
        rect = self.rect()
        margin = self._resize_margin

        edges = Qt.Edge(0)
        if local_pos.x() <= margin:
            edges |= Qt.Edge.LeftEdge
        elif local_pos.x() >= rect.width() - margin:
            edges |= Qt.Edge.RightEdge
        if local_pos.y() <= margin:
            edges |= Qt.Edge.TopEdge
        elif local_pos.y() >= rect.height() - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _cursor_for_edges(self, edges):
        if edges in (
            Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
            Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
        ):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in (
            Qt.Edge.TopEdge | Qt.Edge.RightEdge,
            Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
        ):
            return Qt.CursorShape.SizeBDiagCursor
        if edges in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge):
            return Qt.CursorShape.SizeHorCursor
        if edges in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeVerCursor
        return None

    def _update_resize_cursor(self, obj, event):
        edges = self._edge_at_pos(obj, event)
        cursor_shape = self._cursor_for_edges(edges)
        if cursor_shape is None:
            self.unsetCursor()
        else:
            self.setCursor(cursor_shape)

    def _start_window_resize(self, obj, event):
        edges = self._edge_at_pos(obj, event)
        if edges and event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemResize(edges)
            return True
        return False

    def update_text(self, text, is_final=False):
        if not text: return
        self._asr_updating = True
        try:
            cursor = self.text_edit.textCursor()
            
            # Handle previous partial result replacement
            if hasattr(self, "_partial_marker") and self._partial_marker:
                start_pos, length = self._partial_marker
                cursor.setPosition(start_pos)
                # Select the partial text
                for _ in range(length):
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                self._partial_marker = None

            if is_final:
                cursor.insertText(text)
                self._partial_marker = None
                # Auto-scroll if at the bottom
                self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())
            else:
                start_pos = cursor.position()
                cursor.insertText(text)
                self._partial_marker = (start_pos, len(text))
                # Restore cursor position after the partial insertion
                self.text_edit.setTextCursor(cursor)
                
            self.committed_text = self.text_edit.toPlainText()
        finally:
            self._asr_updating = False

    def clear_text(self):
        self._asr_updating = True
        self.committed_text = ""
        self.text_edit.clear()
        self._asr_updating = False

    def _smart_join(self, base, new_text):
        base = base.strip(); new_text = new_text.strip()
        if not base: return new_text
        if not new_text: return base
        
        # Don't add space if the last char of base is a CJK character or punctuation
        # and the first char of new_text is also CJK.
        last_char = base[-1]
        first_char = new_text[0]
        
        def is_cjk(char):
            # Check for CJK Unified Ideographs, CJK punctuation, etc.
            return any([
                '\u4e00' <= char <= '\u9fff', # Chinese
                '\u3000' <= char <= '\u303f', # CJK Punctuation
                '\u3040' <= char <= '\u30ff', # Japanese Hiragana/Katakana
                '\uff00' <= char <= '\uffef', # Full-width forms
                '\u1100' <= char <= '\u11ff' or '\uac00' <= char <= '\ud7af', # Korean
            ])

        if is_cjk(last_char) or is_cjk(first_char):
            return base + new_text
            
        return base + " " + new_text
