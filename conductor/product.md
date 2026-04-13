# AIinputbox: Product Definition

## Objective
A lightweight, high-performance floating input assistant for Ubuntu Linux designed for seamless text entry and transcription.

## Core Features
1. **Always-on-Top Floating UI**: A frameless, translucent PyQt6 window that is **draggable and resizable**, and can be toggled via a global hotkey, system tray, or **on-screen buttons**.
2. **Dual Input Modes**: Supports both standard keyboard entry and high-accuracy voice input with manual **Start/Stop buttons**.
3. **Local ASR (100% Offline)**: Performs speech recognition entirely on the local machine using `sherpa-onnx` and **Paraformer-Online** (int8). **Models are loaded once at application startup** to ensure instant responsiveness.
4. **Simulated Streaming**: Provides a "real-time" experience by using **Silero VAD v5** for Voice Activity Detection to emit intermediate results as you speak.
5. **Multi-User Safe**: Robust IPC (Inter-Process Communication) that uses user-specific socket paths (`$XDG_RUNTIME_DIR/aiinputbox.socket`) to prevent collisions on shared systems.
6. **Global Hotkey Management**: A reliable listener that handles complex modifier groups (Ctrl, Alt, Shift, Super) across X11 and Wayland (via IPC and OS-level binds).
7. **Input Integration**: Transcribed text is displayed in the floating UI. Pressing **Ctrl+Enter** copies the text to the system clipboard, returns focus to the previous application, pastes there, and clears the input box. Pressing **Esc** toggles recording.
8. **Modern Audio Backend**: Compatibility with **PipeWire** (via PulseAudio emulation) for low-latency, cross-device audio capture.
9. **UI Framework**: PyQt6 with a **Solar** theme.

## Architecture
The project is architected with a strict background-processing model, where the ASR engine and VAD logic run in dedicated worker threads to ensure the UI remains 100% responsive even during heavy inference.
