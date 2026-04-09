import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from ui import main_window as main_window_module


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
            with patch.object(self.window, "_simulate_paste", side_effect=lambda: paste_calls.append("paste")):
                self.window.submit_text()

        self.assertEqual(QApplication.clipboard().text(), "hello world")
        self.assertEqual(paste_calls, ["paste"])
        self.assertEqual(self.window.text_edit.toPlainText(), "")
        self.assertFalse(self.window._pending_submit)

    def test_wayland_paste_prefers_portal_before_legacy_fallbacks(self):
        self.window.portal_keyboard = Mock()
        self.window.portal_keyboard.is_available.return_value = True

        with patch.dict(main_window_module.os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=False):
            with patch.object(self.window, "_start_portal_paste_async") as portal_start:
                with patch.object(main_window_module.subprocess, "run") as run_mock:
                    self.window._simulate_paste()

        portal_start.assert_called_once()
        run_mock.assert_not_called()

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
                    "open_model_manager": ["Ctrl+M"],
                    "hide_window": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
