import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.logging_utils import log
from core.path_utils import get_state_path

try:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except Exception:
    Gio = None
    GLib = None


KEYBOARD_DEVICE = 1
KEY_STATE_RELEASED = 0
KEY_STATE_PRESSED = 1
KEYSYM_CONTROL_L = 0xFFE3
KEYSYM_V = 0x0076
NO_SESSION = "idle"
HELPER_TIMEOUT_SECONDS = 15


class PortalError(RuntimeError):
    pass


@dataclass
class PortalSessionStatus:
    state: str
    session_handle: str | None = None
    devices: int = 0
    persistence_mode: str = "none"
    restore_token_present: bool = False
    last_error: str = ""


@dataclass
class PasteAttemptResult:
    success: bool
    method_used: str
    user_visible_error_shown: bool = False
    should_retry_session: bool = False
    error_message: str = ""


class PortalStateStore:
    def __init__(self, path=None):
        self.path = path or get_state_path("portal_state.json")

    def load(self):
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            log(f"PortalState: failed to load state: {e}")
            return {}

    def save_success(self, restore_token, persistence_mode, devices, backend="remote-desktop"):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        state = self.load()
        state.update(
            {
                "backend": backend,
                "restore_token": restore_token or "",
                "persistence_mode": persistence_mode,
                "devices": int(devices),
                "last_error": "",
                "denied_persist": False,
            }
        )
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def clear_invalid_token(self, reason):
        state = self.load()
        state["restore_token"] = ""
        state["last_error"] = str(reason)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def record_denial(self, reason):
        state = self.load()
        state["denied_persist"] = True
        state["last_error"] = str(reason)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


class WaylandPortalKeyboard:
    BUS_NAME = "org.freedesktop.portal.Desktop"
    DESKTOP_PATH = "/org/freedesktop/portal/desktop"
    REQUEST_IFACE = "org.freedesktop.portal.Request"
    REMOTE_DESKTOP_IFACE = "org.freedesktop.portal.RemoteDesktop"

    def __init__(self, allow_helper_fallback=True, state_store=None):
        self._conn = None
        self._session_handle = None
        self._helper_script = Path(__file__).with_name("wayland_portal_helper.py")
        self._allow_helper_fallback = allow_helper_fallback
        self._state_store = state_store or PortalStateStore()
        self._status = PortalSessionStatus(state=NO_SESSION)
        self._available = (Gio is not None and GLib is not None) or (
            self._allow_helper_fallback and self._helper_script.exists()
        )

    def is_available(self):
        return self._available

    def session_status(self):
        return self._status

    def reset_session(self, reason="reset requested"):
        log(f"Portal: session reset ({reason})")
        self._session_handle = None
        self._status = PortalSessionStatus(state=NO_SESSION, last_error=str(reason))

    def prepare_session(self, parent_window=""):
        if Gio is None or GLib is None:
            raise PortalError("Gio/GLib bindings are unavailable")

        if self._session_handle:
            self._status.state = "ready"
            return self._status

        state_data = self._state_store.load()
        restore_token = state_data.get("restore_token") or ""
        if restore_token:
            try:
                self._status.state = "restoring"
                return self._create_session(parent_window=parent_window, restore_token=restore_token)
            except PortalError as e:
                log(f"Portal: restore failed, rebuilding session: {e}")
                self._state_store.clear_invalid_token(str(e))
                self.reset_session(f"restore failed: {e}")

        self._status.state = "creating"
        return self._create_session(parent_window=parent_window, restore_token="")

    def paste_ctrl_v(self, parent_window=""):
        try:
            if Gio is None or GLib is None:
                if not self._allow_helper_fallback:
                    raise PortalError("Portal helper fallback is disabled")
                self._paste_via_helper(parent_window=parent_window)
                return PasteAttemptResult(success=True, method_used="portal-helper")

            self.prepare_session(parent_window=parent_window)
            self._notify_keysym(KEYSYM_CONTROL_L, KEY_STATE_PRESSED)
            self._notify_keysym(KEYSYM_V, KEY_STATE_PRESSED)
            self._notify_keysym(KEYSYM_V, KEY_STATE_RELEASED)
            self._notify_keysym(KEYSYM_CONTROL_L, KEY_STATE_RELEASED)
            log("Portal: Paste simulated via RemoteDesktop portal")
            return PasteAttemptResult(success=True, method_used="portal")
        except PortalError as e:
            log(f"Portal: paste failed: {e}")
            self.reset_session(str(e))
            return PasteAttemptResult(
                success=False,
                method_used="portal",
                should_retry_session=True,
                error_message=str(e),
            )

    def _paste_via_helper(self, parent_window=""):
        try:
            result = subprocess.run(
                ["python3", "-u", str(self._helper_script), "--parent-window", parent_window or ""],
                check=True,
                capture_output=True,
                text=True,
                timeout=HELPER_TIMEOUT_SECONDS,
            )
            stdout = result.stdout.strip()
            if stdout:
                log(f"Portal: helper output: {stdout}")
            log("Portal: Paste simulated via RemoteDesktop portal helper")
        except subprocess.CalledProcessError as e:
            stdout = (e.stdout or "").strip()
            stderr = (e.stderr or "").strip()
            raise PortalError(
                f"Portal helper failed with exit code {e.returncode}; stdout={stdout!r}; stderr={stderr!r}"
            ) from e
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or "").strip()
            stderr = (e.stderr or "").strip()
            raise PortalError(
                f"Portal helper timed out waiting for portal response; stdout={stdout!r}; stderr={stderr!r}"
            ) from e
        except Exception as e:
            raise PortalError(f"Portal helper failed: {e}") from e

    def _ensure_connection(self):
        if Gio is None or GLib is None:
            raise PortalError("Gio/GLib bindings are unavailable")
        if self._conn is None:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return self._conn

    def _create_session(self, parent_window="", restore_token=""):
        create_options = self._request_options("voxquill_create", include_session_token=True)
        create_request = self._subscribe_request(create_options["handle_token"])
        log("Portal: create_session_sent")
        self._call_sync(
            "CreateSession",
            GLib.Variant("(a{sv})", (create_options,)),
            GLib.VariantType.new("(o)"),
        )
        create_results = self._check_response("CreateSession", self._await_request(create_request))

        session_handle = create_results.get("session_handle")
        if not session_handle:
            raise PortalError("Portal did not return a session handle")

        self._session_handle = session_handle
        self._status = PortalSessionStatus(
            state="selecting_devices",
            session_handle=session_handle,
            restore_token_present=bool(restore_token),
        )

        select_options = self._request_options("voxquill_select")
        select_options["types"] = GLib.Variant("u", KEYBOARD_DEVICE)
        select_options["persist_mode"] = GLib.Variant("u", 2)
        if restore_token:
            select_options["restore_token"] = GLib.Variant("s", restore_token)
        select_request = self._subscribe_request(select_options["handle_token"])
        log("Portal: select_devices_sent")
        self._call_sync(
            "SelectDevices",
            GLib.Variant("(oa{sv})", (self._session_handle, select_options)),
            GLib.VariantType.new("(o)"),
        )
        self._check_response("SelectDevices", self._await_request(select_request))

        start_options = self._request_options("voxquill_start")
        start_request = self._subscribe_request(start_options["handle_token"])
        self._status.state = "starting"
        log("Portal: start_sent")
        self._call_sync(
            "Start",
            GLib.Variant("(osa{sv})", (self._session_handle, parent_window or "", start_options)),
            GLib.VariantType.new("(o)"),
        )
        start_results = self._check_response("Start", self._await_request(start_request))

        devices = int(start_results.get("devices", 0))
        if not devices & KEYBOARD_DEVICE:
            raise PortalError("Portal session started without keyboard permission")

        restore_token = start_results.get("restore_token", "")
        persistence_mode = "persistent" if restore_token else "session"
        self._state_store.save_success(restore_token, persistence_mode, devices)
        self._status = PortalSessionStatus(
            state="ready",
            session_handle=self._session_handle,
            devices=devices,
            persistence_mode=persistence_mode,
            restore_token_present=bool(restore_token),
        )
        log("Portal: session_ready")
        return self._status

    def _notify_keysym(self, keysym, state):
        if not self._session_handle:
            raise PortalError("Portal session is not ready")
        try:
            log("Portal: notify_keysent")
            self._call_sync(
                "NotifyKeyboardKeysym",
                GLib.Variant("(oa{sv}iu)", (self._session_handle, {}, int(keysym), int(state))),
                None,
            )
        except Exception as e:
            raise PortalError(f"NotifyKeyboardKeysym failed: {e}") from e

    def _call_sync(self, method, parameters, reply_type):
        conn = self._ensure_connection()
        return conn.call_sync(
            self.BUS_NAME,
            self.DESKTOP_PATH,
            self.REMOTE_DESKTOP_IFACE,
            method,
            parameters,
            reply_type,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _request_options(self, prefix, include_session_token=False):
        options = {
            "handle_token": GLib.Variant("s", self._token(prefix)),
        }
        if include_session_token:
            options["session_handle_token"] = GLib.Variant("s", self._token(f"{prefix}_session"))
        return options

    def _token(self, prefix):
        return f"{prefix}_{secrets.token_hex(6)}"

    def _subscribe_request(self, handle_token):
        conn = self._ensure_connection()
        request_path = self._request_path(handle_token)
        state = {"response": None, "error": None}

        def on_response(_conn, _sender, _path, _iface, _signal, params, _user_data):
            try:
                response_code, results = params.unpack()
                log(f"Portal: request_response_received code={response_code}")
                state["response"] = {
                    "response": int(response_code),
                    "results": self._deep_unpack(results),
                }
            except Exception as e:
                state["error"] = e
            finally:
                if state["loop"].is_running():
                    state["loop"].quit()

        state["loop"] = GLib.MainLoop()
        state["subscription_id"] = conn.signal_subscribe(
            self.BUS_NAME,
            self.REQUEST_IFACE,
            "Response",
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
            None,
        )
        return state

    def _await_request(self, state, timeout_ms=120000):
        def on_timeout():
            state["error"] = TimeoutError("Portal request timed out")
            if state["loop"].is_running():
                state["loop"].quit()
            return False

        timeout_id = GLib.timeout_add(timeout_ms, on_timeout)
        try:
            state["loop"].run()
        finally:
            GLib.source_remove(timeout_id)
            self._conn.signal_unsubscribe(state["subscription_id"])

        if state["error"] is not None:
            raise PortalError(str(state["error"]))
        if state["response"] is None:
            raise PortalError("Portal request finished without a response")
        return state["response"]

    def _check_response(self, method, response):
        response_code = response["response"]
        if response_code != 0:
            if method == "Start":
                self._state_store.record_denial(f"{method} denied by portal (response={response_code})")
            raise PortalError(f"{method} denied by portal (response={response_code})")
        return response["results"]

    def _request_path(self, handle_token):
        conn = self._ensure_connection()
        if GLib is not None and isinstance(handle_token, GLib.Variant):
            handle_token = handle_token.unpack()
        elif hasattr(handle_token, "unpack") and callable(handle_token.unpack):
            handle_token = handle_token.unpack()
        handle_token = str(handle_token)
        sender = conn.get_unique_name().lstrip(":").replace(".", "_")
        return f"{self.DESKTOP_PATH}/request/{sender}/{handle_token}"

    def _deep_unpack(self, value):
        if isinstance(value, GLib.Variant):
            return self._deep_unpack(value.unpack())
        if isinstance(value, dict):
            return {k: self._deep_unpack(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._deep_unpack(v) for v in value]
        return value
