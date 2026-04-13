# Test Strategy

## Current Test Stack

- Language/runtime: Python 3
- Test runner: `unittest`
- Test directory: `tests/`
- Current focus:
  - UI shortcut semantics
  - Wayland portal session handling
  - model/config behavior

This repository does not yet use YAML test cases as the source of truth. Validation is currently code-first and command-driven.

## Relevant Validation Commands

- Shortcut and UI interaction regression:

```bash
python3 -m unittest tests.test_ui_shortcuts
```

- Portal session and fallback behavior:

```bash
python3 -m unittest tests.test_wayland_portal
```

- Combined validation for the current unsubmitted interaction changes:

```bash
python3 -m unittest tests.test_ui_shortcuts tests.test_wayland_portal
```

## What The Current Validation Covers

- `Esc` toggles recording instead of submitting text.
- `Ctrl+Enter` submits through clipboard plus paste.
- `Ctrl+Shift+Enter` submits through clipboard plus direct typing.
- submit clears non-empty input and hides the window before returning focus.
- Wayland paste prefers Portal and falls back when needed.
- stale Portal attempts can time out and reset.
- UI appearance preferences load, sanitize, persist, and apply.

## Current Gaps

- No YAML case catalog or case-to-test ID linkage exists yet.
- No archived test report structure exists yet.
- No automated live desktop validation exists for real GNOME/Wayland authorization flows.
- Clipboard and focus return are unit-tested, but compositor-specific behavior still requires manual verification on a real session.
