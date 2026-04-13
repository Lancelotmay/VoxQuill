# Track 4: Clipboard & Text Handling

## Goal
Implement the **Ctrl+Enter** submit behavior to copy the current transcription to the system clipboard, return focus to the previous window, paste there, and clear the text buffer. **Esc** should toggle recording only.

## Tasks
1. [ ] **Clipboard Integration (`core/clipboard.py` or within UI)**
   - Use `pyperclip` or `QClipboard` to copy text.
2. [ ] **Shortcut Handlers (`ui/main_window.py`)**
   - Bind `Ctrl+Enter` to submit the current text.
   - Bind `Esc` to toggle recording.
   - If recording is active during submit:
     - Stop recording first.
     - Then copy text, return focus, paste, and clear the input.
3. [ ] **Text Buffer Management**
   - Ensure final results are correctly appended and partial results are shown as temporary feedback.

## Implementation Details
- **Clipboard**: `QApplication.clipboard().setText(text)` is the most direct PyQt method.
- **Focus Return**: Lower/deactivate the floating window so the previously active application regains focus before paste is simulated.

## Success Criteria
- [ ] Transcribing text and then pressing **Ctrl+Enter** copies that text to the clipboard.
- [ ] The previous application regains focus before paste is simulated.
- [ ] Non-empty submit clears the input box.
- [ ] Pressing **Esc** only toggles recording.
