"""silero-vad 流式语音检测"""
import logging

import numpy as np

from config import config

logger = logging.getLogger("diting.vad")

_model = None


def _get_model():
    global _model
    if _model is None:
        from silero_vad import load_silero_vad
        _model = load_silero_vad()
        logger.info("silero-vad 模型就绪")
    return _model


class VoiceActivityDetector:
    _MAX_BUFFER = 30 * 16000  # 最多缓存 30 秒

    def __init__(self):
        self._model = _get_model()
        self._buffer = np.array([], dtype=np.float32)
        self._speaking = False
        self._speech_start = 0
        self._silence_start = 0
        self._clock = 0  # 已处理采样总数
        self._cfg = config.vad

    def process(self, chunk: np.ndarray) -> list[dict]:
        """喂入一块音频，返回已完成的语音段"""
        self._buffer = np.concatenate([self._buffer, chunk])

        # 防溢出
        if len(self._buffer) > self._MAX_BUFFER:
            overflow = len(self._buffer) - self._MAX_BUFFER
            self._buffer = self._buffer[overflow:]
            self._clock += overflow

        segments = []
        min_chunk = 512
        sr = self._cfg.sample_rate

        while len(self._buffer) >= min_chunk:
            frame = self._buffer[:min_chunk]
            try:
                prob = self._model(frame, sr).item()
            except Exception:
                prob = 0.0

            if prob > self._cfg.threshold and not self._speaking:
                self._speaking = True
                self._speech_start = self._clock
                self._silence_start = 0

            elif prob <= self._cfg.threshold and self._speaking:
                if self._silence_start == 0:
                    self._silence_start = self._clock
                silence_samples = self._clock - self._silence_start
                if silence_samples >= self._cfg.min_silence_duration_ms / 1000 * sr:
                    seg = self._cut_segment(self._speech_start, self._silence_start)
                    if seg:
                        segments.append(seg)
                    self._speaking = False
                    self._silence_start = 0

            elif prob > self._cfg.threshold:
                self._silence_start = 0

            self._buffer = self._buffer[min_chunk:]
            self._clock += min_chunk

        return segments

    def flush(self) -> list[dict]:
        segments = []
        if self._speaking:
            seg = self._cut_segment(self._speech_start, self._clock)
            if seg:
                segments.append(seg)
        self.reset()
        return segments

    def reset(self):
        self._buffer = np.array([], dtype=np.float32)
        self._speaking = False
        self._speech_start = 0
        self._silence_start = 0
        self._clock = 0

    def _cut_segment(self, start: int, end: int) -> dict | None:
        pad = int(self._cfg.speech_pad_ms / 1000 * self._cfg.sample_rate)
        min_samples = int(self._cfg.min_speech_duration_ms / 1000 * self._cfg.sample_rate)

        actual_start = max(0, start - pad)
        actual_end = end + pad
        duration = end - start

        if duration < min_samples:
            return None

        # 从 buffer 范围映射到全局采样轴
        buf_start = self._clock - len(self._buffer)
        rel_start = max(0, actual_start - buf_start)
        rel_end = min(len(self._buffer), actual_end - buf_start)

        if rel_end <= rel_start or rel_start >= len(self._buffer):
            return None

        audio = self._buffer[rel_start:rel_end].copy()
        return {
            "audio": audio,
            "start_ms": start / self._cfg.sample_rate * 1000,
            "end_ms": end / self._cfg.sample_rate * 1000,
        }
