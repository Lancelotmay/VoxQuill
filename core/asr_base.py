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

    def _log(self, msg):
        log(f"ASR[{self.model_config['id']}]: {msg}")

    def set_paused(self, paused):
        if paused:
            self.paused = False
            self.should_flush = True
            return

        self.paused = False
        self.should_flush = False
        self.audio_provider.clear_queue()
        self._reset_runtime_state()

    def _reset_runtime_state(self):
        raise NotImplementedError

    def stop(self):
        self.running = False
