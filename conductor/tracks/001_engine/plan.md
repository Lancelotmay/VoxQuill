# Track 1: Core Engine (ASR & VAD)

## Goal
Implement a robust audio processing pipeline that captures audio, detects speech via VAD, and transcribes it in real-time via Paraformer-Online.

## Tasks
1. [ ] **Audio Provider (`core/audio.py`)**
   - Implement `AudioProvider` class using `PyAudio`.
   - Configure for 16kHz, Mono, 16-bit PCM.
   - Use a thread-safe queue to buffer audio chunks.
2. [ ] **ASR Worker (`core/asr.py`)**
   - Implement `ASRWorker` class (QThread or Python Thread).
   - Load Paraformer and VAD models at startup.
   - Process audio chunks from the queue.
   - Handle VAD segmentation (start/end of speech).
3. [ ] **Engine Signal Interface**
   - Define callbacks/signals for `on_partial_result(text)` and `on_final_result(text)`.
   - Implement `stop_audio()` and `start_audio()` manual overrides.

## Implementation Details
- **Chunk Size**: 512 samples (32ms) to match Silero VAD requirement.
- **VAD Logic**: Only feed audio to the Paraformer recognizer when `vad.is_speech` is true.
- **Model Loading**: Initialize models once in the constructor of `ASRWorker`.

## Success Criteria
- [ ] `core/audio.py` can capture audio and print levels.
- [ ] `core/asr.py` correctly transcribes speech into text in real-time.
- [ ] VAD correctly segments silence from speech.
