import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from ui import main_window as main_window_module
from ui import model_manager as model_manager_module
from ui import style as style_module


class AIInputBoxShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.shortcut_path = str(Path(self.tmpdir.name) / "shortcuts.json")
        self.patchers = [
            patch.object(main_window_module, "apply_surface_shadow", lambda *args, **kwargs: None),
            patch.object(main_window_module, "list_available_models", return_value=[]),
            patch.object(main_window_module, "load_asr_config", return_value={"id": "test-model"}),
            patch.object(main_window_module, "get_history_enabled", return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.window = main_window_module.AIInputBox(shortcut_config_path=self.shortcut_path)

    def tearDown(self):
        self.window.close()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tmpdir.cleanup()

    def test_toggle_action_emits_toggle_recording(self):
        calls = []
        self.window.request_toggle_recording.connect(lambda: calls.append("toggle"))

        self.window.trigger_action("toggle_recording", source="test")

        self.assertEqual(calls, ["toggle"])

    def test_submit_action_requests_stop_before_submit_when_recording(self):
        calls = []
        self.window.request_stop_and_submit.connect(lambda: calls.append("stop"))
        self.window.is_recording = True

        self.window.trigger_action("submit_text", source="test")

        self.assertEqual(calls, ["stop"])
        self.assertTrue(self.window._pending_submit)

    def test_submit_text_copies_pastes_and_clears_non_empty_input(self):
        paste_calls = []
        self.window.text_edit.setPlainText("hello world")

        with patch.object(main_window_module.QTimer, "singleShot", side_effect=lambda _delay, fn: fn()):
            with patch.object(self.window, "_simulate_paste", side_effect=lambda _text=None: paste_calls.append("paste")):
                with patch.object(self.window, "hide") as hide_mock:
                    self.window.submit_text()

        self.assertEqual(QApplication.clipboard().text(), "hello world")
        self.assertEqual(paste_calls, ["paste"])
        self.assertEqual(self.window.text_edit.toPlainText(), "")
        self.assertFalse(self.window._pending_submit)
        hide_mock.assert_called_once()

    def test_submit_text_direct_types_and_clears_non_empty_input(self):
        type_calls = []
        self.window.text_edit.setPlainText("hello world")

        with patch.object(main_window_module.QTimer, "singleShot", side_effect=lambda _delay, fn: fn()):
            with patch.object(self.window, "_simulate_direct_input", side_effect=lambda text: type_calls.append(text)):
                with patch.object(self.window, "hide") as hide_mock:
                    self.window.submit_text(mode="type")

        self.assertEqual(QApplication.clipboard().text(), "hello world")
        self.assertEqual(type_calls, ["hello world"])
        self.assertEqual(self.window.text_edit.toPlainText(), "")
        self.assertFalse(self.window._pending_submit)
        hide_mock.assert_called_once()

    def test_wayland_paste_prefers_portal_before_legacy_fallbacks(self):
        self.window.portal_keyboard = Mock()
        self.window.portal_keyboard.is_available.return_value = True

        with patch.dict(main_window_module.os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=False):
            with patch.object(self.window, "_start_portal_paste_async") as portal_start:
                with patch.object(main_window_module.subprocess, "run") as run_mock:
                    self.window._simulate_paste()

        portal_start.assert_called_once()
        run_mock.assert_not_called()

    def test_wayland_direct_input_prefers_wtype(self):
        with patch.dict(main_window_module.os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=False):
            with patch.object(main_window_module.subprocess, "run") as run_mock:
                result = self.window._simulate_direct_input("hello")

        self.assertIsNone(result)
        run_mock.assert_called_once_with(["wtype", "hello"], check=True)

    def test_wayland_direct_input_falls_back_to_pynput(self):
        with patch.dict(main_window_module.os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=False):
            with patch.object(main_window_module.subprocess, "run", side_effect=RuntimeError("missing wtype")):
                with patch.object(self.window, "_simulate_x11_direct_input") as fallback_mock:
                    fallback_mock.return_value = main_window_module.PasteAttemptResult(
                        success=True, method_used="type-pynput"
                    )
                    result = self.window._simulate_wayland_direct_input("hello")

        self.assertTrue(result.success)
        fallback_mock.assert_called_once_with("hello", fallback_label="Wayland fallback")

    def test_portal_failure_falls_back_then_shows_dialog(self):
        self.window.portal_keyboard = Mock()
        self.window.portal_keyboard.paste_ctrl_v.return_value = main_window_module.PasteAttemptResult(
            success=False,
            method_used="portal",
            error_message="boom",
            should_retry_session=True,
        )

        class ImmediateThread:
            def __init__(self, target=None, name=None, daemon=None):
                self._target = target

            def start(self):
                self._target()

        with patch.object(main_window_module.threading, "Thread", ImmediateThread):
            with patch.object(main_window_module.QTimer, "singleShot", side_effect=lambda _delay, fn: fn()):
                with patch.object(
                    self.window,
                    "_simulate_wayland_legacy_paste",
                    return_value=main_window_module.PasteAttemptResult(
                        success=False, method_used="manual", error_message="manual paste required"
                    ),
                ):
                    with patch.object(main_window_module.QMessageBox, "information") as info_mock:
                        self.window._start_portal_paste_async()

        info_mock.assert_called_once()
        self.assertFalse(self.window._portal_paste_inflight)

    def test_portal_async_start_sets_inflight_and_returns(self):
        self.window.portal_keyboard = Mock()
        self.window.portal_keyboard.paste_ctrl_v.return_value = main_window_module.PasteAttemptResult(
            success=True, method_used="portal"
        )
        started = []

        class CaptureThread:
            def __init__(self, target=None, name=None, daemon=None):
                self._target = target
                self.name = name
                self.daemon = daemon

            def start(self):
                started.append((self.name, self.daemon, self._target is not None))

        with patch.object(main_window_module.threading, "Thread", CaptureThread):
            self.window._start_portal_paste_async()

        self.assertEqual(started, [("portal-paste", True, True)])
        self.assertTrue(self.window._portal_paste_inflight)

    def test_portal_watchdog_clears_stale_inflight_and_falls_back(self):
        self.window.portal_keyboard = Mock()
        self.window._portal_paste_inflight = True
        self.window._portal_paste_attempt_id = 4
        self.window._portal_paste_started_at = main_window_module.time.monotonic() - 13

        with patch.object(
            self.window,
            "_simulate_wayland_legacy_paste",
            return_value=main_window_module.PasteAttemptResult(success=True, method_used="legacy-wtype"),
        ) as fallback_mock:
            self.window._check_portal_paste_timeout(4)

        self.window.portal_keyboard.reset_session.assert_called_once()
        self.assertFalse(self.window._portal_paste_inflight)
        fallback_mock.assert_called_once()

    def test_custom_shortcut_config_is_loaded(self):
        with open(self.shortcut_path, "w", encoding="utf-8") as f:
            json.dump({"toggle_recording": ["Ctrl+Shift+R"]}, f)

        manager = main_window_module.ShortcutBindingManager(config_path=self.shortcut_path)
        manager.set_actions(self.window.action_registry.definitions())

        self.assertEqual(manager.bindings()["toggle_recording"], ["Ctrl+Shift+R"])
        self.assertEqual(manager.bindings()["submit_text"], ["Ctrl+Return", "Ctrl+Enter"])
        self.assertEqual(manager.bindings()["submit_text_direct"], ["Ctrl+Shift+Return", "Ctrl+Shift+Enter"])

    def test_conflicting_shortcut_config_falls_back_to_defaults(self):
        with open(self.shortcut_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "toggle_recording": ["Ctrl+Return"],
                    "submit_text": ["Ctrl+Return", "Ctrl+Enter"],
                },
                f,
            )

        manager = main_window_module.ShortcutBindingManager(config_path=self.shortcut_path)
        manager.set_actions(self.window.action_registry.definitions())

        self.assertEqual(manager.bindings()["toggle_recording"], ["Esc"])

    def test_conflicting_custom_shortcuts_are_rejected_on_save(self):
        manager = main_window_module.ShortcutBindingManager(config_path=self.shortcut_path)
        manager.set_actions(self.window.action_registry.definitions())

        with self.assertRaises(ValueError):
            manager.save_bindings(
                {
                    "toggle_recording": ["Ctrl+Shift+R"],
                    "submit_text": ["Ctrl+Shift+R"],
                    "submit_text_direct": ["Ctrl+Shift+Alt+R"],
                    "open_model_manager": ["Ctrl+M"],
                    "hide_window": [],
                }
            )

    def test_window_uses_inactive_opacity_when_visible_but_unfocused(self):
        self.window._inactive_opacity = 0.58

        with patch.object(self.window, "isHidden", return_value=False):
            with patch.object(self.window, "isActiveWindow", return_value=False):
                self.window._update_inactive_visual_state()

        self.assertTrue(self.window.surface.property("inactive"))
        self.assertTrue(self.window.input_container.property("inactive"))

    def test_window_uses_full_opacity_when_active(self):
        self.window._inactive_opacity = 0.58

        with patch.object(self.window, "isHidden", return_value=False):
            with patch.object(self.window, "isActiveWindow", return_value=True):
                self.window._update_inactive_visual_state()

        self.assertFalse(self.window.surface.property("inactive"))
        self.assertFalse(self.window.input_container.property("inactive"))

    def test_restore_after_submit_waits_before_showing_without_focus(self):
        self.window._restore_after_submit_delay_ms = 375

        with patch.object(main_window_module.QTimer, "singleShot") as single_shot:
            self.window._restore_after_submit_without_focus()

        single_shot.assert_called_once_with(375, self.window.bring_to_front_without_focus)

    def test_bring_to_front_without_focus_shows_without_activating(self):
        with patch.object(self.window, "show") as show_mock:
            with patch.object(self.window, "raise_") as raise_mock:
                with patch.object(self.window, "activateWindow") as activate_mock:
                    with patch.object(self.window.text_edit, "setFocus") as set_focus_mock:
                        with patch.object(main_window_module.QTimer, "singleShot"):
                            self.window.bring_to_front_without_focus()

        self.assertTrue(self.window.testAttribute(main_window_module.Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertTrue(self.window.surface.property("inactive"))
        self.assertTrue(self.window.input_container.property("inactive"))
        show_mock.assert_called_once()
        raise_mock.assert_called_once()
        activate_mock.assert_not_called()
        set_focus_mock.assert_not_called()

    def test_x11_paste_schedules_restore_after_attempt(self):
        with patch.dict(main_window_module.os.environ, {}, clear=True):
            with patch.object(self.window, "_simulate_x11_paste", return_value=main_window_module.PasteAttemptResult(success=True, method_used="x11")):
                with patch.object(self.window, "_restore_after_submit_without_focus") as restore_mock:
                    self.window._simulate_paste()

        restore_mock.assert_called_once()

    def test_portal_paste_completion_schedules_restore_after_attempt(self):
        self.window._portal_paste_attempt_id = 7
        self.window._portal_paste_inflight = True

        with patch.object(self.window, "_restore_after_submit_without_focus") as restore_mock:
            self.window._on_portal_paste_finished(
                7,
                main_window_module.PasteAttemptResult(success=True, method_used="portal"),
            )

        restore_mock.assert_called_once()


class UIStyleTests(unittest.TestCase):
    def test_load_ui_preferences_returns_defaults_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prefs = style_module.load_ui_preferences(str(Path(tmpdir) / "missing-ui.json"))

        self.assertEqual(prefs["theme"], "light")
        self.assertEqual(prefs["inactive_opacity"], style_module.DEFAULT_INACTIVE_OPACITY)

    def test_load_ui_preferences_sanitizes_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "ui.json"
            config_path.write_text(
                json.dumps({"theme": "midnight", "inactive_opacity": 4}),
                encoding="utf-8",
            )

            prefs = style_module.load_ui_preferences(str(config_path))

        self.assertEqual(prefs["theme"], "light")
        self.assertEqual(prefs["inactive_opacity"], 1.0)

    def test_load_app_stylesheet_supports_dark_theme(self):
        stylesheet = style_module.load_app_stylesheet(theme="dark", inactive_opacity=0.5)

        self.assertIn("#16181D", stylesheet)
        self.assertIn("rgba(22, 24, 29, 0.500)", stylesheet)
        self.assertNotIn("{{TEXT_PRIMARY}}", stylesheet)

    def test_save_ui_preferences_sanitizes_and_persists_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "ui.json"

            saved = style_module.save_ui_preferences(
                {"theme": "night", "inactive_opacity": -2},
                str(config_path),
            )
            loaded = style_module.load_ui_preferences(str(config_path))

        self.assertEqual(saved["theme"], "light")
        self.assertEqual(saved["inactive_opacity"], 0.1)
        self.assertEqual(loaded, saved)


class ModelManagerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.patchers = [
            patch.object(model_manager_module, "apply_surface_shadow", lambda *args, **kwargs: None),
            patch.object(model_manager_module, "load_asr_config", return_value={"id": "test-model"}),
            patch.object(model_manager_module, "get_model_catalog", return_value=[]),
            patch.object(model_manager_module, "get_global_languages", return_value=["en"]),
            patch.object(model_manager_module, "get_history_enabled", return_value=False),
            patch.object(model_manager_module, "get_history_dir", return_value="/tmp/history"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.dialog = model_manager_module.ModelManagerDialog()

    def tearDown(self):
        self.dialog.close()
        for patcher in reversed(self.patchers):
            patcher.stop()

    def test_save_selection_persists_ui_preferences_and_applies_them(self):
        self.dialog._ui_config_path = "/tmp/test-ui.json"
        self.dialog.theme_combo.setCurrentIndex(self.dialog.theme_combo.findData("dark"))
        self.dialog.inactive_opacity_spin.setValue(0.63)

        with patch.object(model_manager_module, "set_active_model") as set_active_model_mock:
            with patch.object(model_manager_module, "save_ui_preferences", return_value={"theme": "dark", "inactive_opacity": 0.63}) as save_prefs_mock:
                with patch.object(model_manager_module, "load_app_stylesheet", return_value="/* dark */") as stylesheet_mock:
                    with patch.object(self.app, "setStyleSheet") as app_stylesheet_mock:
                        self.dialog._save_selection()

        set_active_model_mock.assert_called_once_with("test-model")
        save_prefs_mock.assert_called_once_with({"theme": "dark", "inactive_opacity": 0.63}, "/tmp/test-ui.json")
        stylesheet_mock.assert_called_once_with(theme="dark", inactive_opacity=0.63)
        app_stylesheet_mock.assert_called_once_with("/* dark */")


if __name__ == "__main__":
    unittest.main()
