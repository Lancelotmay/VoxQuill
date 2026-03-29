# Track 3: UI Development

## Goal
Implement a draggable, resizable PyQt6 floating window with a **Solar** theme, real-time transcription display, and manual Start/Stop buttons.

## Tasks
1. [ ] **Main Window (`ui/main_window.py`)**
   - Create `AIInputBox` class inheriting from `QMainWindow`.
   - Set window flags: `Qt.WindowType.FramelessWindowHint`, `Qt.WindowType.WindowStaysOnTopHint`, `Qt.WindowType.Tool`.
   - Implement window dragging (via `mousePressEvent`/`mouseMoveEvent`).
   - Implement window resizing.
2. [ ] **Solar Theme & Styling (`ui/style.py`)**
   - Define QSS for the Solarized Dark/Light palette.
   - Background: Translucent.
   - Text: Solarized Base0 (Dark mode) or Base00 (Light mode).
3. [ ] **UI Layout**
   - `QTextEdit` or `QLabel` for real-time transcription.
   - `QPushButton` for Start/Stop (with icons or text).
   - `QPushButton` for Close/Clear.
4. [ ] **Engine Integration**
   - Connect `ASRWorker` signals to update the UI text.
   - Connect Start/Stop buttons to `ASRWorker.set_paused()`.

## Implementation Details
- **Resizing**: Use a custom `SizeGrip` or handle edge detection in `mouseMoveEvent`.
- **Transparency**: Use `setWindowOpacity` or `setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)`.

## Success Criteria
- [ ] A frameless window appears that can be moved and resized.
- [ ] The window follows the Solar theme.
- [ ] Clicking Start/Stop controls the ASR engine (visible via logs/UI updates).
