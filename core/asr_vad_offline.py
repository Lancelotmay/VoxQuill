import time

import re
import numpy as np
import sherpa_onnx

from core.asr_base import BaseASRWorker


class VadOfflineASRWorker(BaseASRWorker):
    def __init__(self, audio_provider, model_config, **callbacks):
        self.recognizer = None
        self.vad = None
        self.punct = None
        self.buffer = np.array([], dtype=np.float32)
        self.started = False
        self.started_time = None
        self.offset = 0
        self.window_size = 0
        self.preview_delay = float(model_config.get("preview_delay", 0.2))
        self._chunk_count = 0
        self._last_vad_log_time = 0.0
        super().__init__(audio_provider, model_config, **callbacks)
        self._load_models()

    def _load_models(self):
        t0 = time.time()
        paths = self.model_config["paths"]
        decode = self.model_config.get("decode", {})
        vad_cfg = self.model_config.get("vad", {})
        punct_cfg = self.model_config.get("punct", {})
        kind = self.model_config.get("recognizer_kind", "sense_voice")

        if kind != "sense_voice":
            raise ValueError(f"Unsupported VAD+offline recognizer kind: {kind}")

        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=paths["model"],
            tokens=paths["tokens"],
            num_threads=int(decode.get("num_threads", 2)),
            use_itn=bool(decode.get("use_itn", False)),
            language=decode.get("language", "auto"),
            debug=False,
            hr_rule_fsts=paths.get("hr_rule_fsts", ""),
            hr_lexicon=paths.get("hr_lexicon", ""),
        )

        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = vad_cfg["model"]
        config.silero_vad.threshold = float(vad_cfg.get("threshold", 0.5))
        config.silero_vad.min_silence_duration = float(vad_cfg.get("min_silence_duration", 0.1))
        config.silero_vad.min_speech_duration = float(vad_cfg.get("min_speech_duration", 0.25))
        if "max_speech_duration" in vad_cfg:
            config.silero_vad.max_speech_duration = float(vad_cfg["max_speech_duration"])
        config.sample_rate = self.sample_rate
        self.vad = sherpa_onnx.VoiceActivityDetector(
            config,
            buffer_size_in_seconds=float(vad_cfg.get("buffer_size_in_seconds", 100)),
        )
        punct_model_path = punct_cfg.get("model", "")
        if punct_cfg.get("enabled") and punct_model_path:
            try:
                self._log(f"Loading punctuation model from {punct_model_path}...")
                punct_model_config = sherpa_onnx.OfflinePunctuationModelConfig(
                    ct_transformer=punct_model_path,
                    num_threads=int(punct_cfg.get("num_threads", 2)),
                    debug=False,
                )
                punct_config = sherpa_onnx.OfflinePunctuationConfig(model=punct_model_config)
                self.punct = sherpa_onnx.OfflinePunctuation(punct_config)
                self._log("Punctuation engine successfully loaded and active.")
            except Exception as e:
                self._log(f"Punctuation engine failed to load: {e}")
        self.window_size = config.silero_vad.window_size
        self._log(f"VAD+offline pipeline ready in {time.time() - t0:.2f}s")

    def _reset_runtime_state(self):
        # We no longer wipe the entire buffer to prevent data loss.
        # This is now handled within the run loop by slicing the buffer.
        self.started = False
        self.started_time = None
        self._last_vad_log_time = 0.0

    def run(self):
        self.running = True
        self._log("Worker active.")

        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue

            chunk_bytes = self.audio_provider.get_audio(timeout=0.1)
            if chunk_bytes is None:
                if self.should_flush:
                    self._flush(force=True)
                    self.paused = True
                    self.should_flush = False
                    if self.on_finished:
                        self.on_finished()
                continue

            chunk = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            self._chunk_count += 1
            if chunk.size and self._chunk_count % 50 == 0:
                peak = float(np.max(np.abs(chunk)))
                self._log(
                    f"[Audio] chunk={self._chunk_count} peak={peak:.4f} "
                    f"buffer={len(self.buffer)} offset={self.offset}"
                )
            if self.buffer.size == 0:
                self.buffer = chunk
            else:
                self.buffer = np.concatenate([self.buffer, chunk])

            while self.offset + self.window_size < len(self.buffer):
                self.vad.accept_waveform(self.buffer[self.offset : self.offset + self.window_size])
                if not self.started and self.vad.is_speech_detected():
                    self.started = True
                    self.started_time = time.time()
                    self._log("[Speech] Start")
                self.offset += self.window_size

            if not self.started:
                now = time.time()
                if now - self._last_vad_log_time > 1.5 and len(self.buffer) > 0:
                    peak = float(np.max(np.abs(self.buffer))) if self.buffer.size else 0.0
                    self._log(
                        f"[VAD] waiting chunk={self._chunk_count} peak={peak:.4f} "
                        f"buffer={len(self.buffer)} offset={self.offset}"
                    )
                    self._last_vad_log_time = now
                
                # If we're not speaking, keep a small lookback buffer and trim the rest
                max_lookback = 20 * self.window_size
                if self.offset > max_lookback:
                    keep_from = self.offset - max_lookback
                    self.buffer = self.buffer[keep_from:]
                    self.offset -= keep_from
                continue

            # Preview/Partial result: Only decode if we are in a speech segment
            if self.started_time and time.time() - self.started_time > self.preview_delay:
                # Decode from the Current Offset back to the start of speech (best effort)
                # For SenseVoice offline, we usually just decode the buffer we have
                text = self._decode_samples(self.buffer)
                if text and self.on_partial_result:
                    self.on_partial_result(text)
                self.started_time = time.time()

            while not self.vad.empty():
                segment = self.vad.front.samples
                self.vad.pop()
                text = self._decode_samples(segment)
                if text:
                    self._log(f"[FINAL] {text}")
                    if self.on_final_result:
                        self.on_final_result(text)
                
                # IMPORTANT: Truncate the buffer up to where VAD has processed
                # To prevent missing the start of the next sentence.
                if len(self.buffer) > self.offset:
                    # Keep everything after the point VAD has read
                    self.buffer = self.buffer[self.offset:]
                else:
                    self.buffer = np.array([], dtype=np.float32)
                
                self.offset = 0
                self._reset_runtime_state()

    def _decode_samples(self, samples):
        if samples is None or len(samples) == 0:
            return ""
        stream = self.recognizer.create_stream()
        stream.accept_waveform(self.sample_rate, samples)
        self.recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        
        # Defensive: Strip SenseVoice internal tags if present
        # We strip both <|zh|>... style tags and [noise] style event tags.
        text = re.sub(r"<\|.*?\|>|\[.*?\]", "", text).strip()
        
        # Check if text already has punctuation from SenseVoice
        has_punct = any(c in text for c in "。，？！.?!,")
        
        if text and self.punct and not has_punct:
            try:
                # Use external model as fallback ONLY if native punct is missing
                text = self.punct.add_punctuation(text).strip()
            except Exception as e:
                self._log(f"Punctuation failed: {e}")
        return text

    def _flush(self, force=False):
        # Prevent hallucination from silence lookback buffer: 
        # Only decode during flush if speech has actually been detected.
        if force and self.started and len(self.buffer) > 0:
            text = self._decode_samples(self.buffer)
            if text:
                self._log(f"[FINAL] {text}")
                if self.on_final_result:
                    self.on_final_result(text)
            else:
                peak = float(np.max(np.abs(self.buffer))) if self.buffer.size else 0.0
                self._log(
                    f"[FLUSH] decode empty started={self.started} "
                    f"buffer={len(self.buffer)} peak={peak:.4f}"
                )
        self._reset_runtime_state()
