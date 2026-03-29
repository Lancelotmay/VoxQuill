# AIinputbox: Development Workflow

## 1. Plan Phase
- All major changes start with a plan in `conductor/tracks/<track_id>/plan.md`.
- Use `enter_plan_mode` to draft and discuss plans.

## 2. Implementation Phase
- Follow the "Plan -> Act -> Validate" cycle for each task.
- Ensure all code follows Python PEP 8 standards.
- UI changes should maintain the Catppuccin Mocha aesthetic.

## 3. Testing Phase
- Unit tests for logic (VAD, IPC, ASR workers).
- Integration tests for the full audio-to-text pipeline.
- Manual verification of the floating window on X11 and Wayland.

## 4. Documentation
- Update `README.md` with installation and usage instructions.
- Document any OS-level setup required for global hotkeys.
