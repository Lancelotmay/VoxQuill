# AIinputbox: Tech Stack

## ASR & Audio
- **Engine**: [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (based on Kaldi and FunASR)
- **Models**:
  - `paraformer-online-zh-en-small` (int8 quantized) for ultra-low latency streaming ASR.
  - `silero_vad.onnx` (v5) for robust voice activity detection.
- **Backend**: `PyAudio` (compatible with PulseAudio and PipeWire).

## UI & Desktop
- **Framework**: `PyQt6` (Qt 6.x)
- **Styling**: QSS (Qt Style Sheets) with a Solar theme.
- **IPC**: Unix Domain Sockets (standard on Linux/Unix).
- **Text Injection**: System Clipboard (via `pyperclip` or `QtClipboard`).

## Runtime Environment
- **Platform**: Ubuntu Linux (22.04+)
- **Display Protocols**: X11 and Wayland.
- **Python**: 3.10+
- **Dependency Management**: `pip` (standard `requirements.txt`).

## Desktop Standards
- **XDG Base Directory**: For sockets, config, and cache files.
- **DBus**: For system-level global shortcut support (optional/future enhancement).
