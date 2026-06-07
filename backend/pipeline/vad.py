"""silero-vad 流式语音检测"""
import logging
import numpy as np
from config import config

logger = logging.getLogger("diting.vad")

_model = None
_torch = None


def _get_model():
    global _model
    if _model is None:
        from silero_vad import load_silero_vad
        _model = load_silero_vad()
        logger.info("silero-vad 就绪")
    return _model


def _get_torch():
    global _torch
    if _torch is None:
        import torch
        _torch = torch
    return _torch


class VoiceActivityDetector:
    _MAX_BUFFER_SAMPLES = 30 * 16000

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def __init__(self):
        self._model = _get_model()
        self._audio_buffer = np.array([], dtype=np.float32)
        self._process_pos = 0
        self._speaking = False
        self._speech_start_sample = 0
        self._silence_start_sample = None
        self._cfg = config.vad

    @property
    def _silence_limit_samples(self) -> int:
        return int(self._cfg.min_silence_duration_ms / 1000 * self._cfg.sample_rate)

    @property
    def _speech_min_samples(self) -> int:
        return int(self._cfg.min_speech_duration_ms / 1000 * self._cfg.sample_rate)

    @property
    def _pad_samples(self) -> int:
        return int(self._cfg.speech_pad_ms / 1000 * self._cfg.sample_rate)

    def process(self, chunk: np.ndarray) -> list[dict]:
        self._audio_buffer = np.concatenate([self._audio_buffer, chunk])

        if len(self._audio_buffer) > self._MAX_BUFFER_SAMPLES:
            overflow = len(self._audio_buffer) - self._MAX_BUFFER_SAMPLES
            self._audio_buffer = self._audio_buffer[overflow:]
            self._process_pos = max(0, self._process_pos - overflow)

            if self._speaking:
                if self._speech_start_sample < overflow:
                    self._speaking = False
                    self._speech_start_sample = 0
                    self._silence_start_sample = None
                else:
                    self._speech_start_sample -= overflow
                    if self._silence_start_sample is not None:
                        if self._silence_start_sample < overflow:
                            self._silence_start_sample = None
                        else:
                            self._silence_start_sample -= overflow

        segments = []
        step = 512
        sr = self._cfg.sample_rate

        while self._process_pos + step <= len(self._audio_buffer):
            frame = self._audio_buffer[self._process_pos:self._process_pos + step]
            cur = self._process_pos
            prob = self._infer(frame, sr)

            if prob > self._cfg.threshold and not self._speaking:
                self._speaking = True
                self._speech_start_sample = cur
                self._silence_start_sample = None

            elif prob <= self._cfg.threshold and self._speaking:
                if self._silence_start_sample is None:
                    self._silence_start_sample = cur
                if cur + step - self._silence_start_sample >= self._silence_limit_samples:
                    seg = self._cut(self._speech_start_sample, self._silence_start_sample)
                    if seg:
                        segments.append(seg)
                    remove = cur + step
                    self._audio_buffer = self._audio_buffer[remove:]
                    self._process_pos = 0
                    self._speaking = False
                    self._speech_start_sample = 0
                    self._silence_start_sample = None
                    continue

            elif prob > self._cfg.threshold:
                self._silence_start_sample = None

            self._process_pos += step

        return segments

    def flush(self) -> list[dict]:
        segments = []
        if self._speaking:
            seg = self._cut(self._speech_start_sample, len(self._audio_buffer))
            if seg:
                segments.append(seg)
        self.reset()
        return segments

    def reset(self):
        self._audio_buffer = np.array([], dtype=np.float32)
        self._process_pos = 0
        self._speaking = False
        self._speech_start_sample = 0
        self._silence_start_sample = None

    def _infer(self, frame: np.ndarray, sr: int) -> float:
        try:
            torch = _get_torch()
            return self._model(torch.from_numpy(frame), sr).item()
        except Exception:
            return 0.0

    def _cut(self, start_sample: int, end_sample: int) -> dict | None:
        if end_sample - start_sample < self._speech_min_samples:
            return None
        actual_start = max(0, start_sample - self._pad_samples)
        actual_end = min(len(self._audio_buffer), end_sample + self._pad_samples)
        if actual_end <= actual_start:
            return None
        return {
            "audio": self._audio_buffer[actual_start:actual_end].copy(),
            "start_ms": start_sample / self._cfg.sample_rate * 1000,
            "end_ms": end_sample / self._cfg.sample_rate * 1000,
        }
