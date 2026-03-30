import threading
import time

from core.logging_utils import log


class BaseASRWorker(threading.Thread):
    def __init__(
        self,
        audio_provider,
        model_config,
        on_partial_result=None,
        on_final_result=None,
        on_finished=None,
    ):
        super().__init__()
        self.audio_provider = audio_provider
        self.model_config = model_config
        self.on_partial_result = on_partial_result
        self.on_final_result = on_final_result
        self.on_finished = on_finished
        self.running = False
        self.paused = False
        self.should_flush = False
        self.sample_rate = int(model_config.get("sample_rate", 16000))
        self._punc_history = ""

    def _log(self, msg):
        log(f"ASR[{self.model_config['id']}]: {msg}")

    def _is_cjk(self, char):
        # Includes Chinese Hanzi and Japanese Kana
        return any([
            '\u4e00' <= char <= '\u9fff',   # CJK Unified Ideographs
            '\u3040' <= char <= '\u30ff',   # Japanese Hiragana/Katakana
            '\uff00' <= char <= '\uffef',   # Full-width forms
        ])

    def _is_korean(self, char):
        return '\u1100' <= char <= '\u11ff' or '\uac00' <= char <= '\ud7af'

    def _is_alnum_or_cjk(self, char):
        return char.isalnum()

    def _extract_punc_delta(self, full_punc, history_raw):
        if not history_raw:
            return full_punc
        
        # Strip chars in full_punc until we match history_raw length (ignoring non-alnum)
        history_chars = [c for c in history_raw if self._is_alnum_or_cjk(c)]
        history_len = len(history_chars)
        
        count = 0
        idx = 0
        while count < history_len and idx < len(full_punc):
            if self._is_alnum_or_cjk(full_punc[idx]):
                count += 1
            idx += 1
        
        # The remainder is the delta, containing the punctuation for the new part
        return full_punc[idx:]

    def _localize_punctuation(self, text):
        if not text:
            return text
        # Count characters by language group
        zh_jp_count = sum(1 for c in text if self._is_cjk(c))
        ko_count = sum(1 for c in text if self._is_korean(c))
        en_count = sum(1 for c in text if 'a' <= c.lower() <= 'z')
        
        # If primarily English or Korean, use Western punctuation.
        # Chinese and Japanese keep CJK punctuation marks (。，).
        if en_count > zh_jp_count or ko_count > zh_jp_count:
            mapping = {
                "。": ".",
                "，": ",",
                "！": "!",
                "？": "?",
                "：": ":",
                "；": ";",
                "“": "\"",
                "”": "\"",
            }
            for zh, en in mapping.items():
                text = text.replace(zh, en)
        return text

    def set_paused(self, paused):
        if paused:
            # When pausing (stopping recording), trigger flush
            self.should_flush = True
            return

        self.paused = False
        self.should_flush = False
        self._punc_history = "" # Reset history for new recording session
        self.audio_provider.clear_queue()
        self._reset_runtime_state()

    def _reset_runtime_state(self):
        raise NotImplementedError

    def stop(self):
        self.running = False
