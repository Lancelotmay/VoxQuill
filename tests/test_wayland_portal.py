import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import wayland_portal


class PortalStateStoreTests(unittest.TestCase):
    def test_save_and_clear_restore_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = wayland_portal.PortalStateStore(path=str(Path(tmpdir) / "portal_state.json"))

            store.save_success("token-1", "persistent", 1)
            self.assertEqual(store.load()["restore_token"], "token-1")

            store.clear_invalid_token("stale")
            state = store.load()
            self.assertEqual(state["restore_token"], "")
            self.assertEqual(state["last_error"], "stale")


class WaylandPortalTests(unittest.TestCase):
    def test_request_path_unpacks_variant_handle_token(self):
        keyboard = wayland_portal.WaylandPortalKeyboard(allow_helper_fallback=False)

        class FakeConn:
            def get_unique_name(self):
                return ":1.42"

        class FakeVariant:
            def __init__(self, value):
                self._value = value

            def unpack(self):
                return self._value

        with patch.object(keyboard, "_ensure_connection", return_value=FakeConn()):
            request_path = keyboard._request_path(FakeVariant("voxquill_create_abc123"))

        self.assertEqual(
            request_path,
            "/org/freedesktop/portal/desktop/request/1_42/voxquill_create_abc123",
        )

    def test_helper_fallback_runs_when_gio_unavailable(self):
        keyboard = wayland_portal.WaylandPortalKeyboard()

        with patch.object(wayland_portal, "Gio", None):
            with patch.object(wayland_portal, "GLib", None):
                with patch.object(wayland_portal.subprocess, "run") as run_mock:
                    run_mock.return_value.stdout = "portal-helper-ok\n"
                    result = keyboard.paste_ctrl_v(parent_window="")

        self.assertTrue(result.success)
        run_mock.assert_called_once()
        args = run_mock.call_args.args[0]
        self.assertEqual(args[0], "python3")
        self.assertEqual(args[1], "-u")
        self.assertTrue(args[2].endswith("core/wayland_portal_helper.py"))
        self.assertEqual(args[3:], ["--parent-window", ""])

    def test_helper_does_not_recurse_when_fallback_disabled(self):
        keyboard = wayland_portal.WaylandPortalKeyboard(allow_helper_fallback=False)

        with patch.object(wayland_portal, "Gio", None):
            with patch.object(wayland_portal, "GLib", None):
                with patch.object(wayland_portal.subprocess, "run") as run_mock:
                    result = keyboard.paste_ctrl_v(parent_window="")

        self.assertFalse(result.success)
        self.assertIn("disabled", result.error_message)
        run_mock.assert_not_called()

    def test_prepare_session_uses_restore_token_then_rotates_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = str(Path(tmpdir) / "portal_state.json")
            store = wayland_portal.PortalStateStore(path=state_path)
            store.save_success("old-token", "persistent", 1)
            keyboard = wayland_portal.WaylandPortalKeyboard(state_store=store)

            calls = []

            def fake_request_options(prefix, include_session_token=False):
                return {
                    "handle_token": prefix,
                    **({"session_handle_token": f"{prefix}_session"} if include_session_token else {}),
                }

            def fake_subscribe(handle_token):
                return handle_token

            def fake_await(state, timeout_ms=120000):
                return state

            def fake_check(method, response):
                return response["results"]

            def fake_call_sync(method, parameters, reply_type):
                calls.append((method, parameters))
                return None

            responses = {
                "voxquill_create": {"response": 0, "results": {"session_handle": "/session/1"}},
                "voxquill_select": {"response": 0, "results": {}},
                "voxquill_start": {"response": 0, "results": {"devices": 1, "restore_token": "new-token"}},
            }

            with patch.object(wayland_portal, "Gio", object()):
                with patch.object(wayland_portal, "GLib", None):
                    pass

            class FakeVariant:
                def __init__(self, _signature, value):
                    self.value = value

            class FakeVariantType:
                @staticmethod
                def new(_value):
                    return None

            fake_glib = type(
                "FakeGLib",
                (),
                {"Variant": FakeVariant, "VariantType": FakeVariantType},
            )

            with patch.object(wayland_portal, "Gio", type("FakeGio", (), {})):
                with patch.object(wayland_portal, "GLib", fake_glib):
                    with patch.object(keyboard, "_request_options", side_effect=fake_request_options):
                        with patch.object(keyboard, "_subscribe_request", side_effect=fake_subscribe):
                            with patch.object(keyboard, "_await_request", side_effect=lambda state: responses[state]):
                                with patch.object(keyboard, "_check_response", side_effect=fake_check):
                                    with patch.object(keyboard, "_call_sync", side_effect=fake_call_sync):
                                        status = keyboard.prepare_session(parent_window="")

            self.assertEqual(status.state, "ready")
            self.assertTrue(status.restore_token_present)
            self.assertEqual(store.load()["restore_token"], "new-token")
            select_call = next(item for item in calls if item[0] == "SelectDevices")
            _, parameters = select_call
            self.assertEqual(parameters.value[1]["restore_token"].value, "old-token")

    def test_paste_failure_resets_session(self):
        keyboard = wayland_portal.WaylandPortalKeyboard(allow_helper_fallback=False)
        keyboard._session_handle = "/session/1"

        with patch.object(wayland_portal, "Gio", type("FakeGio", (), {})):
            with patch.object(wayland_portal, "GLib", type("FakeGLib", (), {})):
                with patch.object(keyboard, "prepare_session"):
                    with patch.object(keyboard, "_notify_keysym", side_effect=wayland_portal.PortalError("boom")):
                        result = keyboard.paste_ctrl_v(parent_window="")

        self.assertFalse(result.success)
        self.assertEqual(keyboard.session_status().state, "idle")
        self.assertIn("boom", result.error_message)


if __name__ == "__main__":
    unittest.main()
