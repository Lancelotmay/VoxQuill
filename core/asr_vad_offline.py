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
        self.started = False
        self.started_time = None
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
            except Exception as e:
                self._log(f"Punctuation engine failed to load: {e}")

        self._log(f"VAD+offline pipeline ready in {time.time() - t0:.2f}s")

    def _reset_runtime_state(self):
        self.started = False
        self.started_time = None
        self._last_vad_log_time = 0.0
        if self.vad:
            self.vad.reset()

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
                self._log(f"[Audio] chunk={self._chunk_count} peak={peak:.4f}")

            if chunk.size:
                self.vad.accept_waveform(chunk)

            if not self.started and self.vad.is_speech_detected():
                self.started = True
                self.started_time = time.time()
                self._log("[Speech] Start")

            if not self.started:
                now = time.time()
                if now - self._last_vad_log_time > 1.5:
                    self._log(f"[VAD] waiting chunk={self._chunk_count}")
                    self._last_vad_log_time = now
                continue

            # Preview/Partial result: Only decode if we are in a speech segment
            if self.started_time and time.time() - self.started_time > self.preview_delay:
                # Use native current_segment.samples to get the entire currently spoken utterance
                samples = self.vad.current_segment.samples
                text = self._decode_samples(samples, is_final=False)
                if text and self.on_partial_result:
                    self.on_partial_result(text)
                self.started_time = time.time()

            while not self.vad.empty():
                segment = self.vad.front.samples
                self.vad.pop()
                
                text = self._decode_samples(segment, is_final=True)
                if text:
                    self._log(f"[FINAL] {text}")
                    if self.on_final_result:
                        self.on_final_result(text)
                
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

        # Only strip native punctuation if a separate punctuation model is active.
        # This prevents "Double Punctuation" while allowing native punctuation if desired.
        if self.punct:
            text = re.sub(r"[。，？！,?!]", "", text)
            # Selective dot stripping: only strip dots if not between digits (to preserve 1.5 etc)
            text = re.sub(r"(?<!\d)\.(?!\d)|((?<=\d)\.(?!\d))|((?<!\d)\.(?=\d))", "", text)

        if self.punct:
            try:
                # Option 2: Sliding Window Logic
                # Prepend raw history for context
                context_raw = ""
                if self._punc_history:
                    last_hist_char = self._punc_history[-1]
                    first_text_char = text[0]
                    # Add space if both are non-CJK (likely English/Western)
                    if not self._is_cjk(last_hist_char) and not self._is_cjk(first_text_char):
                        context_raw = self._punc_history + " "
                    else:
                        context_raw = self._punc_history
                
                full_raw = context_raw + text

                self._log(f"[Punc] Applying context (history_len={len(self._punc_history)}) is_final={is_final}")
                self._log(f"[DEBUG] Raw stripped segment: '{text}'")
                full_punc = self.punct.add_punctuation(full_raw).strip()
                self._log(f"[DEBUG] Full punctuated: '{full_punc[:200]}...'") # Cap log display 
                
                # Extract the newly punctuated part corresponding to the current chunk
                text = self._extract_punc_delta(full_punc, self._punc_history)
                
                # Only strip leading punctuation from the delta if the punctuated history
                # already ended with a mark. This prevents duplicates (e.g. 。。) while
                # allowing the punctuator to provide a junction mark if one was missing.
                history_end_punc = re.search(r'[。，？！.?!, ]+$', full_punc[:len(full_punc)-len(text)])
                if history_end_punc:
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
        if force and self.vad:
            self.vad.flush()
            while not self.vad.empty():
                segment = self.vad.front.samples
                self.vad.pop()
                text = self._decode_samples(segment, is_final=True)
                if text:
                    self._log(f"[FINAL FLUSH] {text}")
                    if self.on_final_result:
                        self.on_final_result(text)
        self._reset_runtime_state()
