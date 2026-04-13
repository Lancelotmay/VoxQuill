# Track 5: System Integration

## Goal
Finalize the application with a system tray icon, instructions for global hotkey integration, and end-to-end testing.

## Tasks
1. [ ] **System Tray Icon (`ui/tray.py`)**
   - Implement `SystemTrayIcon` using `QSystemTrayIcon`.
   - Add menu: "Show", "Hide", "Toggle Recording", "Quit".
2. [ ] **Global Hotkey Documentation (`README.md`)**
   - Provide clear instructions for Ubuntu/GNOME:
     - Go to Settings -> Keyboard -> Keyboard Shortcuts -> Custom Shortcuts.
     - Command: `python3 /path/to/cli.py --command toggle`.
3. [ ] **Final Polish**
   - Ensure `main.py` properly initializes the tray icon.
   - Test resizing/dragging persistence (optional).
   - Verify Wayland vs X11 behavior.

## Implementation Details
- **Tray Icon**: Use a simple SVG or a colored square for Solar theme compatibility.

## Success Criteria
- [ ] Application starts minimized to tray (optional) or with tray visible.
- [ ] CLI command correctly toggles the UI from a background state.
- [ ] End-to-end flow: Trigger -> Speak -> Ctrl+Enter -> Paste (Ctrl+V) works flawlessly, while Esc only toggles recording.
