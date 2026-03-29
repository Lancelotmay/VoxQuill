# Track 4: Clipboard & Text Handling

## Goal
Implement the **Esc** key behavior to copy the current transcription to the system clipboard, hide the window, and clear the text buffer.

## Tasks
1. [ ] **Clipboard Integration (`core/clipboard.py` or within UI)**
   - Use `pyperclip` or `QClipboard` to copy text.
2. [ ] **ESC Key Handler (`ui/main_window.py`)**
   - Override `keyPressEvent` in `AIInputBox`.
   - If `key == Qt.Key.Key_Escape`:
     - Copy text from `QTextEdit`.
     - Call `clear_text()`.
     - Hide the window.
3. [ ] **Text Buffer Management**
   - Ensure final results are correctly appended and partial results are shown as temporary feedback.

## Implementation Details
- **Clipboard**: `QApplication.clipboard().setText(text)` is the most direct PyQt method.
- **Visual Feedback**: Briefly change the title or show a tooltip when text is copied.

## Success Criteria
- [ ] Transcribing text and then pressing **Esc** copies that text to the clipboard.
- [ ] The UI clears and hides after **Esc**.
- [ ] Manual verification using `Ctrl+V` in another application.
