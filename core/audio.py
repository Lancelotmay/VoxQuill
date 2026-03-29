import pyaudio
import queue
import threading
import numpy as np

from core.logging_utils import log

class AudioProvider:
    def __init__(self, sample_rate=16000, chunk_size=512):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.audio_queue = queue.Queue()
        self.is_running = False
        self._callback_count = 0
        self._max_abs_seen = 0.0
        self.input_device_index = None
        self.input_device_info = None
        self.capture_sample_rate = sample_rate
        self.capture_chunk_size = chunk_size

    def _audio_callback(self, in_data, frame_count, time_info, status):
        if self.is_running:
            self._callback_count += 1
            samples = np.frombuffer(in_data, dtype=np.int16)
            if samples.size:
                peak = float(np.max(np.abs(samples))) / 32768.0
                if peak > self._max_abs_seen:
                    self._max_abs_seen = peak
                if self._callback_count % 50 == 0:
                    log(
                        "Audio: callback="
                        f"{self._callback_count} peak={peak:.4f} max_peak={self._max_abs_seen:.4f} "
                        f"queue={self.audio_queue.qsize()} status={status} "
                        f"capture_rate={self.capture_sample_rate}"
                    )
                if self.capture_sample_rate != self.sample_rate:
                    samples = self._resample_int16(samples, self.capture_sample_rate, self.sample_rate)
                self.audio_queue.put(samples.tobytes())
        return (None, pyaudio.paContinue)

    def start(self):
        if self.stream: return
        try:
            self.is_running = True
            self._callback_count = 0
            self._max_abs_seen = 0.0
            self.input_device_index, self.input_device_info = self._select_input_device()
            self.capture_sample_rate = int(float(self.input_device_info.get("defaultSampleRate", self.sample_rate)))
            self.capture_chunk_size = max(1, int(round(self.chunk_size * self.capture_sample_rate / self.sample_rate)))
            self.stream = self.audio.open(
                format=pyaudio.paInt16, channels=1, rate=self.capture_sample_rate,
                input=True, frames_per_buffer=self.capture_chunk_size,
                input_device_index=self.input_device_index,
                stream_callback=self._audio_callback
            )
            self.stream.start_stream()
            device_name = self.input_device_info.get("name", "unknown") if self.input_device_info else "unknown"
            device_rate = self.input_device_info.get("defaultSampleRate") if self.input_device_info else "unknown"
            log(
                f"Audio: Stream started target_rate={self.sample_rate}Hz "
                f"device_index={self.input_device_index} device='{device_name}' "
                f"device_rate={device_rate} capture_rate={self.capture_sample_rate} "
                f"capture_chunk={self.capture_chunk_size}"
            )
            return True
        except Exception as e:
            log(f"Audio: Failed to start stream: {e}")
            self.is_running = False
            self.stream = None
            self.input_device_index = None
            self.input_device_info = None
            self.capture_sample_rate = self.sample_rate
            self.capture_chunk_size = self.chunk_size
            return False

    def stop(self):
        self.is_running = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except: pass
            self.stream = None
        log(
            "Audio: Stream stopped. "
            f"callbacks={self._callback_count} max_peak={self._max_abs_seen:.4f} "
            f"remaining_queue={self.audio_queue.qsize()}"
        )

    def get_audio(self, timeout=None):
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_queue(self):
        count = 0
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                count += 1
            except queue.Empty:
                break
        if count > 0:
            log(f"Audio: Cleared {count} stale chunks from queue.")

    def qsize(self):
        return self.audio_queue.qsize()

    def _select_input_device(self):
        try:
            default_info = self.audio.get_default_input_device_info()
        except Exception as e:
            log(f"Audio: No default input device info available: {e}")
            return None, None

        default_index = int(default_info["index"])
        default_name = str(default_info.get("name", "")).strip().lower()
        input_devices = []
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                input_devices.append(info)

        abstract_candidates = [
            info for info in input_devices
            if str(info.get("name", "")).strip().lower() in {"default", "pipewire", "pulse", "pulseaudio"}
        ]
        hardware_candidates = [
            info for info in input_devices
            if str(info.get("name", "")).strip().lower() not in {"default", "pipewire", "pulse", "pulseaudio"}
        ]

        selected = default_info
        reason = "system default input"
        if default_name in {"default", "pipewire", "pulse", "pulseaudio"}:
            selected = default_info
            reason = "preferred abstract Linux audio device"
        elif abstract_candidates:
            selected = abstract_candidates[0]
            reason = "preferred abstract Linux audio device"
        elif hardware_candidates:
            selected = hardware_candidates[0]
            reason = "fallback hardware input device"

        log(
            "Audio: Selected input device "
            f"index={selected.get('index')} name='{selected.get('name')}' "
            f"max_input={selected.get('maxInputChannels')} default_rate={selected.get('defaultSampleRate')} "
            f"reason='{reason}'"
        )
        return int(selected["index"]), selected

    def _resample_int16(self, samples, src_rate, dst_rate):
        if samples.size == 0 or src_rate == dst_rate:
            return samples

        src = samples.astype(np.float32)
        src_len = src.shape[0]
        dst_len = max(1, int(round(src_len * dst_rate / src_rate)))
        src_x = np.arange(src_len, dtype=np.float32)
        dst_x = np.linspace(0, src_len - 1, num=dst_len, dtype=np.float32)
        resampled = np.interp(dst_x, src_x, src)
        return np.clip(np.round(resampled), -32768, 32767).astype(np.int16)

    def __del__(self):
        self.stop()
        self.audio.terminate()
