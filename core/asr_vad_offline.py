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
        self._speech_start_offset = 0
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
        self._speech_start_offset = 0
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
                    # Include 0.25s of pre-roll (8 windows) to catch the start of soft words
                    pre_roll = 8 * self.window_size
                    self._speech_start_offset = max(0, self.offset - pre_roll)
                    self._log(f"[Speech] Start (pre-roll offset={self._speech_start_offset})")
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
                max_lookback = 12 * self.window_size # ~0.4s
                if self.offset > max_lookback:
                    keep_from = self.offset - max_lookback
                    self.buffer = self.buffer[keep_from:]
                    self.offset -= keep_from
                continue

            # Preview/Partial result: Only decode if we are in a speech segment
            if self.started_time and time.time() - self.started_time > self.preview_delay:
                # Use tracked offset to ensure consistency with final result
                text = self._decode_samples(self.buffer[self._speech_start_offset:], is_final=False)
                if text and self.on_partial_result:
                    self.on_partial_result(text)
                self.started_time = time.time()

            while not self.vad.empty():
                segment = self.vad.front.samples
                self.vad.pop()
                
                # To ensure 'Final' result captures the same 'pre-roll' as 'Partial' result:
                # We prepend the audio from our tracked start offset to the VAD processed head
                # if the VAD didn't already include it. 
                # Since VAD segments are pops, we approximate the join.
                # Simplest robust way: Trust our tracked offset.
                if self.buffer.size > 0:
                    # We take the audio from _speech_start_offset to the current offset
                    # but since VAD might have advanced, we take the whole buffer we have
                    # which corresponds to the current segment.
                    segment = self.buffer[:self.offset]

                text = self._decode_samples(segment, is_final=True)
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

    def _decode_samples(self, samples, is_final=False):
        if samples is None or len(samples) == 0:
            return ""
        stream = self.recognizer.create_stream()
        stream.accept_waveform(self.sample_rate, samples)
        self.recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        
        # Defensive: Strip SenseVoice internal tags if present
        # We strip both <|zh|>... style tags and [noise] style event tags.
        text = re.sub(r"<\|.*?\|>|\[.*?\]", "", text).strip()
        
        if not text:
            return ""

        # Pre-strip native punctuation to let Scheme 2 have full control.
        # This prevents "Double Punctuation" where both SenseVoice and Punc model add marks.
        # We preserve alphanumeric and CJK, stripping common punctuation.
        text = re.sub(r"[。，？！,?!]", "", text)
        # Selective dot stripping: only strip dots if not between digits (to preserve 1.5 etc)
        text = re.sub(r"(?<!\d)\.(?!\d)|((?<=\d)\.(?!\d))|((?<!\d)\.(?=\d))", "", text)

        if self.punct:
            try:
                # Option 2: Sliding Window Logic
                # Prepend raw history for context
                if self._punc_history:
                    last_hist_char = self._punc_history[-1]
                    first_text_char = text[0]
                    # Add space if both are non-CJK (likely English/Western)
                    if not self._is_cjk(last_hist_char) and not self._is_cjk(first_text_char):
                        full_raw = self._punc_history + " " + text
                    else:
                        full_raw = self._punc_history + text
                else:
                    full_raw = text

                self._log(f"[Punc] Applying context (history_len={len(self._punc_history)}) is_final={is_final}")
                self._log(f"[DEBUG] Raw stripped segment: '{text}'")
                full_punc = self.punct.add_punctuation(full_raw).strip()
                self._log(f"[DEBUG] Full punctuated: '{full_punc[:200]}...'") # Cap log display 
                
                # Extract the newly punctuated part corresponding to the current chunk
                text = self._extract_punc_delta(full_punc, self._punc_history)
                
                # Strip leading punctuation from the delta to avoid duplicates at junctions (e.g. 。。)
                # The punctuation model often 'closes' the history part, and we don't want that join-mark.
                text = text.lstrip("。，？！,?!. ")

                # Update history (Raw text only) ONLY if this is a final segment
                if is_final:
                    self._punc_history = full_raw[-200:] # Reduced from 512 to 200
            except Exception as e:
                self._log(f"Context punctuation failed: {e}")
        
        # Clean up any rare double-punctuation artifacts (like 。。) from the final output
        text = re.sub(r'([。，？！.?!,])\1+', r'\1', text)
        return self._localize_punctuation(text.strip())

    def _flush(self, force=False):
        # Prevent hallucination from silence lookback buffer: 
        # Only decode during flush if speech has actually been detected.
        if force and self.started and len(self.buffer) > 0:
            text = self._decode_samples(self.buffer, is_final=True)
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
