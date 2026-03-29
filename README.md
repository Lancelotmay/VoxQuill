# VoxQuill

A Linux-based desktop utility for voice-to-text input, specialized for AI prompting workflows. 

**Author**: Lancelot MEI

> [!NOTE]
> This project is developed with extensive assistance from AI. Contributions, fixes, and issue reports are highly encouraged and welcome.

## Technical Overview

VoxQuill provides a floating, frameless interface for capturing voice input and converting it to text using local ASR engines. It is designed to minimize friction and prevent accidental "Enter" triggers when drafting prompts for AI LLM interfaces.

### Core Stack
- **UI Framework**: PyQt6
- **ASR Engine**: [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (ONNX runtime)
- **Voice Activity Detection**: Silero VAD v5
- **IPC Protocol**: Unix Domain Sockets (JSON-based)
- **Audio I/O**: PyAudio
- **OS Support**: Only tested on Ubuntu + Wayland.

## Features

- **Offline Processing**: All transcription is performed locally; no audio data is transmitted externally.
- **Model Management**: Currently only supports `sensevoice small`.
- **In-place Expansion**: Detects pre-defined command prefixes (e.g. `//s `) in the text buffer and expands them into full prompt templates.
- **IPC-based Control**: Includes a CLI tool (`cli.py`) to trigger actions from desktop-level global hotkeys.
- **Automated Workflow**: On `Esc`, the window automatically copies the current buffer to the system clipboard and simulates a paste (`Ctrl+V`) into the previously active application (Note: Known limitation on Wayland).

## Known Issues (Ubuntu + Wayland)

- **Window Positioning**: Unable to automatically move the window to the current cursor's screen/position.
- **Auto-Paste**: Pressing `Esc` cannot directly paste content to the cursor position in the target window.


## Installation

### 1. System Dependencies
Ensure `libxcb-cursor0` is installed for correct window positioning on Wayland.

### 2. Environment Setup
```bash
git clone https://github.com/youruser/VoxQuill.git
cd VoxQuill
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Model Acquisition
Models can be downloaded directly through the application's **Model Manager** (Ctrl + M) after starting the program. 

Alternatively, you can run the utility script to manually download the default models:
```bash
python3 scripts/download_models.py
```

## Usage

### Execution
Start the main process:
```bash
python3 main.py
```

### Global Hotkey Configuration
Map a global shortcut in your Desktop Environment to the following command:
```bash
/path/to/VoxQuill/.venv/bin/python /path/to/VoxQuill/cli.py --command toggle
```

### Keyboard Interactions
- **Esc**: Stop recording, copy text, hide window, and simulate paste.
- **Control + M**: Open Model Manager to switch or download ASR engines.
- **Manual Toggle**: Use the record button in the UI to start/stop listening.

## Configuration

### Prompt Templates
Custom command prefixes and their expansions are defined in `config/prompts.json`.

### ASR Configuration
Model paths and pipeline settings are managed in `config/asr_models.json`.

## Build & Metadata

### Packaging
To generate a standalone Linux executable using PyInstaller:
```bash
./scripts/build_linux.sh
```

### License
GNU GPL v3.0
