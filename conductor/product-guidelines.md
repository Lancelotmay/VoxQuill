# AIinputbox: Product Guidelines

## Core Principles
1. **Offline-First**: All ASR processing MUST happen locally. No cloud APIs.
2. **Instant Readiness**: **Models MUST be pre-loaded at startup**; voice input should be ready to capture audio immediately without loading overhead.
3. **Esc to Clipboard**: Pressing the **Esc** key must copy the current transcription to the clipboard and reset/hide the UI.
4. **Minimalist UI**: The floating window should be as unobtrusive as possible while providing clear feedback.
3. **Speed over Precision**: Prioritize Paraformer-Online's low-latency "real-time" experience over extremely large, high-precision models.
4. **Privacy & Security**: Use user-specific socket paths (`$XDG_RUNTIME_DIR/aiinputbox.socket`). Never log or transmit transcribed text.
5. **Cross-Protocol Support**: Ensure seamless operation on both X11 and Wayland environments.

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
