# AIinputbox: Product Guidelines

## Core Principles
1. **Offline-First**: All ASR processing MUST happen locally. No cloud APIs.
2. **Instant Readiness**: **Models MUST be pre-loaded at startup**; voice input should be ready to capture audio immediately without loading overhead.
3. **Ctrl+Enter to Submit**: Pressing **Ctrl+Enter** must copy the current transcription to the clipboard, return focus to the previous application, paste there, and clear the input box.
4. **Esc to Toggle Recording**: Pressing **Esc** must only start or stop recording.
5. **Minimalist UI**: The floating window should be as unobtrusive as possible while providing clear feedback.
6. **Speed over Precision**: Prioritize Paraformer-Online's low-latency "real-time" experience over extremely large, high-precision models.
7. **Privacy & Security**: Use user-specific socket paths (`$XDG_RUNTIME_DIR/aiinputbox.socket`). Never log or transmit transcribed text.
8. **Cross-Protocol Support**: Ensure seamless operation on both X11 and Wayland environments.

## Visual Identity
- **Theme**: Solar (Solarized Dark/Light inspired).
- **Accents**: Cyan or Orange for active states.
- **Interactivity**: 
    - Frameless window must be draggable (via mouse press/move).
    - Window borders or corners must allow resizing.
    - Prominent Start/Stop buttons for voice input.

## Accessibility
- High-contrast mode compatibility.
- Clear visual indicators for VAD (voice active vs. idle).
- Configurable hotkeys to avoid conflict with existing system shortcuts.
