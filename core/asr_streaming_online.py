import os
import time

import numpy as np
import sherpa_onnx

from core.asr_base import BaseASRWorker


class StreamingOnlineASRWorker(BaseASRWorker):
    def __init__(self, audio_provider, model_config, **callbacks):
        self.is_in_speech = False
        self.last_speech_time = time.time()
        self.last_partial_text = ""
        self.last_partial_change_time = time.time()
        self.has_previewed_punct = False
        self.recognizer = None
        self.vad = None
        self.punct = None
        self.stream = None
        super().__init__(audio_provider, model_config, **callbacks)
        self._load_models()

    def _load_models(self):
        t0 = time.time()
        paths = self.model_config["paths"]
        decode = self.model_config.get("decode", {})
        endpoint = self.model_config.get("endpoint", {})
        vad_cfg = self.model_config.get("vad", {})
        punct_cfg = self.model_config.get("punct", {})
        kind = self.model_config.get("recognizer_kind", "paraformer")

        if kind != "paraformer":
            raise ValueError(f"Unsupported streaming recognizer kind: {kind}")

        self.recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
            encoder=paths["encoder"],
            decoder=paths["decoder"],
            tokens=paths["tokens"],
            num_threads=int(decode.get("num_threads", 4)),
            sample_rate=self.sample_rate,
            feature_dim=int(self.model_config.get("feature_dim", 80)),
            decoding_method=decode.get("decoding_method", "greedy_search"),
            debug=False,
            enable_endpoint_detection=bool(endpoint.get("enabled", True)),
            rule1_min_trailing_silence=float(endpoint.get("rule1_min_trailing_silence", 2.4)),
            rule2_min_trailing_silence=float(endpoint.get("rule2_min_trailing_silence", 1.2)),
            rule3_min_utterance_length=float(endpoint.get("rule3_min_utterance_length", 30.0)),
        )

        if vad_cfg.get("enabled", True):
            config = sherpa_onnx.VadModelConfig()
            config.silero_vad.model = vad_cfg["model"]
            config.silero_vad.threshold = float(vad_cfg.get("threshold", 0.5))
            config.silero_vad.min_silence_duration = float(vad_cfg.get("min_silence_duration", 0.5))
            config.silero_vad.min_speech_duration = float(vad_cfg.get("min_speech_duration", 0.25))
            if "max_speech_duration" in vad_cfg:
                config.silero_vad.max_speech_duration = float(vad_cfg["max_speech_duration"])
            config.sample_rate = self.sample_rate
            self.vad = sherpa_onnx.VoiceActivityDetector(
                config,
                buffer_size_in_seconds=float(vad_cfg.get("buffer_size_in_seconds", 60)),
            )

        punct_model_path = punct_cfg.get("model", "")
        if punct_cfg.get("enabled") and punct_model_path and os.path.exists(punct_model_path):
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

        self.stream = self.recognizer.create_stream()
        self._log(f"Streaming pipeline ready in {time.time() - t0:.2f}s")

    def _reset_runtime_state(self):
        self.stream = self.recognizer.create_stream()
        self.is_in_speech = False
        self.last_speech_time = time.time()
        self.last_partial_text = ""
        self.last_partial_change_time = time.time()
        self.has_previewed_punct = False

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
                    self._check_finalization(force=True)
                    self.paused = True
                    self.should_flush = False
                    if self.on_finished:
                        self.on_finished()
                else:
                    self._check_finalization()
                continue

            chunk_array = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            if self.vad is None:
                self._accept_stream_chunk(chunk_array)
            else:
                self.vad.accept_waveform(chunk_array)
                while not self.vad.empty():
                    self._accept_stream_chunk(self.vad.front.samples)
                    self.vad.pop()

            self._check_finalization()

    def _accept_stream_chunk(self, samples):
        if not self.is_in_speech:
            self._log("[Speech] Start")
        self.is_in_speech = True
        self.last_speech_time = time.time()

        self.stream.accept_waveform(self.sample_rate, samples)
        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)

        result = self.recognizer.get_result(self.stream)
        text = (result if isinstance(result, str) else result.text).strip()
        if text:
            if text != self.last_partial_text:
                if self.on_partial_result:
                    self.on_partial_result(text)
                self.last_partial_text = text
                self.last_partial_change_time = time.time()
                self.has_previewed_punct = False
            elif (time.time() - self.last_partial_change_time > 0.8) and not self.has_previewed_punct:
                if self.punct:
                    try:
                        punctuated = self.punct.add_punctuation(text).strip()
                        if self.on_partial_result:
                            self.on_partial_result(punctuated)
                        self.has_previewed_punct = True
                    except Exception:
                        pass

        if self.recognizer.is_endpoint(self.stream):
            self._log("[Endpoint] Semantic boundary detected")
            self._check_finalization(force=True)

    def _check_finalization(self, force=False):
        is_silence = self.vad is not None and not self.vad.is_speech_detected()
        silence_duration = time.time() - self.last_speech_time
        silence_trigger = is_silence and silence_duration > 1.2

        if self.is_in_speech and (force or silence_trigger):
            padding = np.zeros(int(self.sample_rate * 0.8), dtype=np.float32)
            self.stream.accept_waveform(self.sample_rate, padding)

            try:
                self.stream.input_finished()
            except Exception:
                pass

            while self.recognizer.is_ready(self.stream):
                self.recognizer.decode_stream(self.stream)

            result = self.recognizer.get_result(self.stream)
            text = (result if isinstance(result, str) else result.text).strip()

            if text:
                if self.punct:
                    try:
                        text = self.punct.add_punctuation(text).strip()
                    except Exception:
                        pass
                self._log(f"[FINAL] {text}")
                if self.on_final_result:
                    self.on_final_result(text)

            self._reset_runtime_state()
