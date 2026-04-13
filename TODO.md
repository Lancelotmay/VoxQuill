# TODO

## Current Task Status

- `Ctrl+Enter` submit flow is implemented:
  - stop recording if active
  - copy text to clipboard
  - return focus to the previous window
  - attempt auto-paste
  - clear the input box after non-empty submit
- `Esc` now only toggles recording.
- Documentation has been updated to reflect the new shortcut semantics.
- Wayland paste priority has been changed to:
  - XDG Desktop Portal first
  - legacy fallback (`wtype` / `evdev-uinput` / `pynput`) second
- A second submit path is now implemented:
  - `Ctrl+Shift+Enter` / `Ctrl+Shift+Return`
  - copies text to the clipboard first
  - then attempts direct keystroke injection instead of paste
  - intended for terminals or apps where `Ctrl+V` is unreliable
- UI appearance preferences are now configurable and persisted in `config/ui.json`:
  - theme selection: `light` / `dark`
  - inactive opacity for the unfocused-but-visible window state
  - preferences are edited in Model Manager and applied immediately after save
- The main window now has an explicit "inactive visual state":
  - after submit it can reappear without stealing focus
  - opacity and styling differ between active and inactive states
- Focused tests were added for shortcut behavior and portal fallback behavior.

## Unsubmitted Change Summary

This worktree currently contains one coherent but still-unreleased batch of changes:

1. Submission semantics were redefined.
   - `Esc` is no longer overloaded for submit.
   - submit is now explicit and separated into paste mode and direct-input mode.
   - recording stop, clipboard sync, focus return, submit attempt, and editor cleanup are handled as one pipeline.

2. Wayland input delivery was reworked.
   - paste mode prefers XDG Desktop Portal RemoteDesktop.
   - direct-input mode prefers `wtype`.
   - legacy fallbacks remain in place for degraded environments.

3. Window behavior became stateful rather than binary.
   - the UI can stay visible in an unfocused, dimmed state after submit.
   - the non-activating restore path is now part of the interaction model.

4. Appearance moved into runtime configuration.
   - theme and inactive opacity are loaded on startup.
   - the Model Manager now also functions as the appearance settings entry point.
   - settings are persisted independently from model and shortcut configuration.

5. Documentation and tests were expanded to match the new interaction model.
   - docs now describe shortcut semantics, submit guarantees, and appearance settings.
   - tests cover the new shortcut, direct-input path, inactive visual state, and UI preference persistence.

## Current Blocker

- Wayland auto-paste is still not production-ready.
- The Portal path starts, but on GNOME/Wayland it does not complete correctly yet:
  - no visible authorization dialog appears
  - the portal request can remain in-flight
  - later submits may be blocked by `portal paste already in flight`
- The previous UI-freeze risk from synchronous helper execution has been mitigated by moving portal paste work to a background thread.
- A UI watchdog timeout and stale in-flight reset path now exist, but they still need real GNOME/Wayland confirmation.

## Next Steps

1. Re-test on GNOME/Wayland and confirm:
   - authorization dialog appears when needed
   - successful authorization leads to auto-paste
   - failure is logged clearly and falls back cleanly
2. Pass a real `parent_window` identifier instead of an empty value.
3. Verify whether `portal paste already in flight` still occurs in real desktop usage after the watchdog reset changes.
4. If Portal still does not complete, capture and analyze the `CreateSession`, `SelectDevices`, and `Start` log sequence from a live run.
