import os
import json
import re
import time
import subprocess
import threading
try:
    import pyperclip
except ImportError:
    pyperclip = None
try:
    import evdev
    from evdev import UInput, ecodes
except ImportError:
    evdev = None
    UInput = None
    ecodes = None
try:
    from pynput.keyboard import Controller, Key
except Exception:
    Controller = None
    Key = None
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QApplication,
    QMenu,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QEvent
from PyQt6.QtGui import QTextCursor, QCursor, QIcon
from core.asr_config import list_available_models, load_asr_config, get_history_dir, get_history_enabled
from core.logging_utils import log
from core.wayland_portal import WaylandPortalKeyboard, PasteAttemptResult
from ui.style import apply_surface_shadow, load_ui_preferences
from ui.model_manager import ModelManagerDialog
from core.path_utils import get_resource_path, get_config_path
from ui.actions import ActionDefinition, ActionRegistry
from ui.shortcut_bindings import ShortcutBindingManager
from datetime import datetime

class AIInputBox(QMainWindow):
    request_stop_and_submit = pyqtSignal()
    request_toggle_recording = pyqtSignal()
    portal_paste_finished = pyqtSignal(int, object)

    def __init__(self, shortcut_config_path=None, ui_config_path=None):
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
        self._pending_submit = False
        self._pending_submit_mode = "paste"
        self._prompts = {}
        self._models = []
        self._resize_margin = 4
        self.keyboard = Controller() if Controller else None
        self.portal_keyboard = WaylandPortalKeyboard()
        self._portal_paste_inflight = False
        self._portal_paste_started_at = 0.0
        self._portal_paste_attempt_id = 0
        self._restore_after_submit_delay_ms = 250
        self._inactive_visual_state = None
        self._action_registry = ActionRegistry()
        self._shortcut_manager = ShortcutBindingManager(config_path=shortcut_config_path or get_config_path("shortcuts.json"))
        self._ui_preferences = load_ui_preferences(ui_config_path or get_config_path("ui.json"))
        self._inactive_opacity = self._ui_preferences["inactive_opacity"]

        self._load_prompts()
        self._load_models()
        
        self.setWindowIcon(QIcon(get_resource_path("resource/main_small_color.png")))
        
        # Pre-generate icons
        self.idle_icon = QIcon(get_resource_path("resource/main_small_color_blue_256.png"))
        self.recording_icon = QIcon(get_resource_path("resource/main_small_color_256.png"))
        
        self._setup_ui()
        self._setup_actions()
        self.portal_paste_finished.connect(self._on_portal_paste_finished)
        self.center_on_screen()
        self._update_inactive_visual_state()

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
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.show()
        self._set_inactive_visual_state(False)
        # On Linux, some WMs ignore activateWindow, so we try multiple tricks
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()
        # Force set focus to text edit
        self.text_edit.setFocus()
        QTimer.singleShot(50, lambda: self.activateWindow())

    def bring_to_front_without_focus(self):
        self.text_edit.clearFocus()
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.show()
        self.raise_()
        self._set_inactive_visual_state(True)
        QTimer.singleShot(0, self._update_inactive_visual_state)

    def _restore_after_submit_without_focus(self):
        QTimer.singleShot(self._restore_after_submit_delay_ms, self.bring_to_front_without_focus)

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
        self.model_button.clicked.connect(lambda: self.trigger_action("open_model_manager", source="button"))
        header_layout.addWidget(self.model_button)
        
        header_layout.addSpacing(4)

        # Direct shortcuts for top 9 commands
        top_commands = list(self._prompts.items())[:9]
        for p_id, p_data in top_commands:
            btn = QPushButton(p_data["label"])
            btn.setObjectName("CommandButton")
            btn.setToolTip(f"Command: {p_data['command']}")
            btn.clicked.connect(lambda checked, text=p_data["text"]: self._run_insert_prompt_action(text, source="button"))
            header_layout.addWidget(btn)
        
        # Unified menu for additional commands
        if len(self._prompts) > 9:
            self.more_button = QPushButton("More")
            self.more_button.setObjectName("MoreButton")
            
            self.menu = QMenu(self)
            for p_id, p_data in list(self._prompts.items())[9:]:
                action = self.menu.addAction(p_data["label"])
                action.setToolTip(f"Command: {p_data['command']}")
                action.triggered.connect(
                    lambda checked, text=p_data["text"]: self._run_insert_prompt_action(text, source="menu")
                )
            
            self.more_button.setMenu(self.menu)
            header_layout.addWidget(self.more_button)
        
        header_layout.addStretch()
        
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("CloseButton")
        self.close_button.setFixedSize(26, 26)
        self.close_button.clicked.connect(lambda: self.trigger_action("hide_window", source="button"))
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

    def _setup_actions(self):
        self._action_registry.register(
            ActionDefinition(
                action_id="submit_text",
                display_name="Submit Text",
                handler=self._handle_submit_action,
                default_shortcuts=("Ctrl+Return", "Ctrl+Enter"),
            )
        )
        self._action_registry.register(
            ActionDefinition(
                action_id="submit_text_direct",
                display_name="Submit Text Direct",
                handler=self._handle_submit_direct_action,
                default_shortcuts=("Ctrl+Shift+Return", "Ctrl+Shift+Enter"),
            )
        )
        self._action_registry.register(
            ActionDefinition(
                action_id="toggle_recording",
                display_name="Toggle Recording",
                handler=self._handle_toggle_recording_action,
                default_shortcuts=("Esc",),
            )
        )
        self._action_registry.register(
            ActionDefinition(
                action_id="open_model_manager",
                display_name="Open Model Manager",
                handler=self._open_model_manager,
                default_shortcuts=("Ctrl+M",),
            )
        )
        self._action_registry.register(
            ActionDefinition(
                action_id="hide_window",
                display_name="Hide Window",
                handler=self.hide,
                default_shortcuts=(),
                user_configurable=False,
            )
        )
        self._shortcut_manager.set_actions(self._action_registry.definitions())
        self._shortcut_manager.apply_to_window(self, self.trigger_action)

    @property
    def action_registry(self):
        return self._action_registry

    @property
    def shortcut_manager(self):
        return self._shortcut_manager

    def trigger_action(self, action_id, source="unknown"):
        return self._action_registry.trigger(action_id, source=source)

    def _handle_toggle_recording_action(self):
        self.request_toggle_recording.emit()

    def _handle_submit_action(self):
        self._handle_submit(mode="paste")

    def _handle_submit_direct_action(self):
        self._handle_submit(mode="type")

    def _handle_submit(self, mode="paste"):
        self._pending_submit_mode = mode
        if self.is_recording:
            self._pending_submit = True
            self.request_stop_and_submit.emit()
        else:
            self.submit_text(mode=mode)

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
        if self._pending_submit:
            QTimer.singleShot(100, lambda: self.submit_text(mode=self._pending_submit_mode))

    def _return_focus_to_previous_window(self):
        # On Wayland, lowering an always-on-top tool window is often not enough to
        # return input focus to the previously active application. Hide the window
        # completely so the compositor can restore focus to another surface.
        self.text_edit.clearFocus()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowActive)
        self.hide()
        log("UI: Hiding window to return focus to previous application")

    def _set_inactive_visual_state(self, inactive):
        if self._inactive_visual_state == inactive:
            return
        self._inactive_visual_state = inactive
        for widget in (self.surface, self.input_container):
            widget.setProperty("inactive", inactive)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _update_inactive_visual_state(self):
        self._set_inactive_visual_state((not self.isHidden()) and (not self.isActiveWindow()))

    def apply_ui_preferences(self, preferences):
        self._ui_preferences = preferences
        self._inactive_opacity = preferences["inactive_opacity"]
        self._update_inactive_visual_state()

    def submit_text(self, mode="paste"):
        text = self.text_edit.toPlainText().strip()

        self._return_focus_to_previous_window()

        if text:
            QApplication.clipboard().setText(text)
            if pyperclip:
                try:
                    pyperclip.copy(text)
                except Exception as e:
                    log(f"UI: pyperclip failed: {e}")

            submit_callback = self._simulate_direct_input if mode == "type" else self._simulate_paste
            QTimer.singleShot(250, lambda: submit_callback(text))
            self._save_to_history(text)

            self.clear_text()

        self._pending_submit = False
        self._pending_submit_mode = "paste"

    def _simulate_paste(self, _text=None):
        is_wayland = "WAYLAND_DISPLAY" in os.environ
        if is_wayland:
            if self.portal_keyboard.is_available():
                self._start_portal_paste_async()
                return

            self._handle_failed_paste_attempt(
                PasteAttemptResult(success=False, method_used="portal", error_message="Portal backend unavailable")
            )
            self._restore_after_submit_without_focus()
            return

        result = self._simulate_x11_paste()
        if not result.success:
            self._show_paste_failure_dialog(result.error_message or "Paste failed")
        self._restore_after_submit_without_focus()

    def _simulate_direct_input(self, text):
        is_wayland = "WAYLAND_DISPLAY" in os.environ
        result = self._simulate_wayland_direct_input(text) if is_wayland else self._simulate_x11_direct_input(text)
        if not result.success:
            self._show_paste_failure_dialog(result.error_message or "Direct input failed")
        self._restore_after_submit_without_focus()

    def _start_portal_paste_async(self):
        if self._portal_paste_inflight:
            if self._portal_paste_is_stale():
                log("UI: stale portal paste detected, resetting session")
                self.portal_keyboard.reset_session("stale in-flight portal paste")
                self._portal_paste_inflight = False
            else:
                log("UI: portal paste already in flight")
                return

        self._portal_paste_inflight = True
        self._portal_paste_started_at = time.monotonic()
        self._portal_paste_attempt_id += 1
        attempt_id = self._portal_paste_attempt_id
        QTimer.singleShot(12000, lambda attempt_id=attempt_id: self._check_portal_paste_timeout(attempt_id))
        log("UI: Starting portal keyboard injection in background")

        def worker():
            try:
                result = self.portal_keyboard.paste_ctrl_v(parent_window=self._portal_parent_window_identifier())
            except Exception as e:
                log(f"UI: portal keyboard injection failed unexpectedly: {e}")
                result = PasteAttemptResult(
                    success=False,
                    method_used="portal",
                    should_retry_session=True,
                    error_message=str(e),
                )
            self.portal_paste_finished.emit(attempt_id, result)

        threading.Thread(target=worker, name="portal-paste", daemon=True).start()

    def _portal_paste_is_stale(self):
        return self._portal_paste_inflight and (time.monotonic() - self._portal_paste_started_at) > 12.0

    def _check_portal_paste_timeout(self, attempt_id):
        if attempt_id != self._portal_paste_attempt_id or not self._portal_paste_inflight:
            return
        if not self._portal_paste_is_stale():
            return

        log("UI: portal paste timed out in UI watchdog")
        self.portal_keyboard.reset_session("UI watchdog timeout")
        self._portal_paste_inflight = False
        self._handle_failed_paste_attempt(
            PasteAttemptResult(
                success=False,
                method_used="portal",
                should_retry_session=True,
                error_message="Portal authorization did not complete in time.",
            )
        )
        self._restore_after_submit_without_focus()

    def _on_portal_paste_finished(self, attempt_id, result):
        if attempt_id != self._portal_paste_attempt_id:
            log("UI: ignoring stale portal paste result from older attempt")
            return
        self._portal_paste_inflight = False
        if not result.success:
            self._handle_failed_paste_attempt(result)
        self._restore_after_submit_without_focus()

    def _handle_failed_paste_attempt(self, result):
        log(f"UI: handling failed paste attempt ({result.method_used}): {result.error_message}")
        fallback_result = self._simulate_wayland_legacy_paste()
        if not fallback_result.success:
            self._show_paste_failure_dialog(
                fallback_result.error_message or result.error_message or "Automatic paste failed"
            )

    def _simulate_wayland_legacy_paste(self):
        try:
            subprocess.run(["wtype", "-M", "ctrl", "v", "-m", "ctrl"], check=True)
            log("UI: Paste simulated via wtype (Wayland)")
            return PasteAttemptResult(success=True, method_used="legacy-wtype")
        except Exception as e:
            log(f"UI: wtype failed: {e}")

        if evdev and UInput is not None and ecodes is not None:
            try:
                cap = {
                    ecodes.EV_KEY: [ecodes.KEY_LEFTCTRL, ecodes.KEY_V]
                }
                with UInput(cap, name="VoxQuill-Virtual-KB") as ui:
                    time.sleep(0.005)
                    ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
                    ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
                    ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
                    ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
                    ui.syn()
                    log("UI: Paste simulated via evdev (Wayland/uinput)")
                    return PasteAttemptResult(success=True, method_used="legacy-evdev")
            except Exception as e:
                log(f"UI: evdev failed: {e}")
        else:
            log("UI: evdev not available")

        return self._simulate_x11_paste(fallback_label="X11 fallback")

    def _simulate_x11_paste(self, fallback_label="X11"):
        if not self.keyboard or Key is None:
            log("UI: pynput keyboard controller unavailable")
            return PasteAttemptResult(
                success=False,
                method_used="manual",
                error_message="Clipboard updated, but automatic paste is unavailable. Press Ctrl+V manually.",
            )

        try:
            with self.keyboard.pressed(Key.ctrl):
                self.keyboard.press('v')
                self.keyboard.release('v')
            log(f"UI: Paste simulated via pynput ({fallback_label})")
            return PasteAttemptResult(success=True, method_used="legacy-pynput")
        except Exception as e:
            log(f"UI: Paste failed: {e}")
            return PasteAttemptResult(
                success=False,
                method_used="manual",
                error_message=f"Clipboard updated, but automatic paste failed ({e}). Press Ctrl+V manually.",
            )

    def _simulate_wayland_direct_input(self, text):
        try:
            subprocess.run(["wtype", text], check=True)
            log("UI: Text typed via wtype (Wayland)")
            return PasteAttemptResult(success=True, method_used="type-wtype")
        except Exception as e:
            log(f"UI: wtype direct input failed: {e}")

        return self._simulate_x11_direct_input(text, fallback_label="Wayland fallback")

    def _simulate_x11_direct_input(self, text, fallback_label="X11"):
        if not self.keyboard:
            log("UI: pynput keyboard controller unavailable for direct input")
            return PasteAttemptResult(
                success=False,
                method_used="manual",
                error_message="Clipboard updated, but direct typing is unavailable.",
            )

        try:
            self.keyboard.type(text)
            log(f"UI: Text typed via pynput ({fallback_label})")
            return PasteAttemptResult(success=True, method_used="type-pynput")
        except Exception as e:
            log(f"UI: direct typing failed: {e}")
            return PasteAttemptResult(
                success=False,
                method_used="manual",
                error_message=f"Clipboard updated, but direct typing failed ({e}).",
            )

    def _show_paste_failure_dialog(self, message):
        QMessageBox.information(
            self,
            "Auto-Paste Failed",
            f"{message}\n\nThe text is already in the clipboard. Press Ctrl+V manually to paste it.",
        )

    def _portal_parent_window_identifier(self):
        if "WAYLAND_DISPLAY" in os.environ:
            return ""
        try:
            return f"x11:{int(self.winId()):x}"
        except Exception:
            return ""

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

    def _run_insert_prompt_action(self, prompt_text, source="unknown"):
        self._action_registry.register(
            ActionDefinition(
                action_id="insert_prompt_runtime",
                display_name="Insert Prompt",
                handler=lambda prompt_text=prompt_text: self._insert_prompt(prompt_text),
                default_shortcuts=(),
                user_configurable=False,
            )
        )
        self.trigger_action("insert_prompt_runtime", source=source)

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

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            self._update_inactive_visual_state()
        super().changeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._update_inactive_visual_state)

    def hideEvent(self, event):
        self._set_inactive_visual_state(False)
        super().hideEvent(event)

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
