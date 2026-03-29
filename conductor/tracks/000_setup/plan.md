# Track 0: Project Setup & Models

## Goal
Set up the Python environment and download the necessary `sherpa-onnx` and VAD models.

## Tasks
1. [ ] **Environment Setup**
   - Initialize a Python 3.10+ virtual environment.
   - Install core dependencies: `sherpa-onnx`, `PyQt6`, `PyAudio`, `pynput`, `numpy`.
2. [ ] **Model Downloader**
   - Create a Python script (`scripts/download_models.py`) to download and extract:
     - [Paraformer-Online ZH-EN (Small, int8)](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-2023-09-14.tar.bz2) (Note: Check for the small/int8 version)
     - [Silero VAD v5 (ONNX)](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx)
3. [ ] **Model Verification**
   - Write a simple test script (`tests/verify_models.py`) to load the models and ensure they are ready for inference.

## Implementation Details
- **Virtual Env**: Use `python3 -m venv .venv`.
- **Requirements**: Create `requirements.txt`.
- **Model Path**: Store models in `models/` directory.

## Success Criteria
- [ ] `requirements.txt` exists and all dependencies are installed.
- [ ] `models/` directory contains both the ASR and VAD models.
- [ ] `verify_models.py` runs successfully.
