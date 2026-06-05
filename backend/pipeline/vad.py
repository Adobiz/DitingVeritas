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
        self._speech_start = 0.0  # 秒
        self._silence_start = 0.0
        self._clock = 0.0  # 秒（已处理时长）
        self._cfg = config.vad

    @property
    def _silence_limit(self) -> float:
        return self._cfg.min_silence_duration_ms / 1000

    @property
    def _speech_min(self) -> float:
        return self._cfg.min_speech_duration_ms / 1000

    @property
    def _pad(self) -> float:
        return self._cfg.speech_pad_ms / 1000

    def process(self, chunk: np.ndarray) -> list[dict]:
        """喂入一块音频，返回已完成的语音段"""
        self._buffer = np.concatenate([self._buffer, chunk])

        # 防溢出：丢弃最旧数据并重置状态（避免 _speech_start 指向已丢弃数据）
        if len(self._buffer) > self._MAX_BUFFER:
            overflow = len(self._buffer) - self._MAX_BUFFER
            self._buffer = self._buffer[overflow:]
            self._clock += overflow / self._cfg.sample_rate
            self._speaking = False
            self._speech_start = 0.0
            self._silence_start = 0.0

        segments = []
        min_chunk = 512
        sr = self._cfg.sample_rate
        step_s = min_chunk / sr  # 每帧时长（秒）

        while len(self._buffer) >= min_chunk:
            frame = self._buffer[:min_chunk]
            try:
                import torch
                t = torch.from_numpy(frame)
                prob = self._model(t, sr).item()
            except Exception:
                prob = 0.0

            if prob > self._cfg.threshold and not self._speaking:
                self._speaking = True
                self._speech_start = self._clock
                self._silence_start = 0.0

            elif prob <= self._cfg.threshold and self._speaking:
                if self._silence_start == 0.0:
                    self._silence_start = self._clock
                if self._clock - self._silence_start >= self._silence_limit:
                    seg = self._cut_segment(self._speech_start, self._silence_start)
                    if seg:
                        segments.append(seg)
                    self._speaking = False
                    self._silence_start = 0.0

            elif prob > self._cfg.threshold:
                self._silence_start = 0.0

            self._buffer = self._buffer[min_chunk:]
            self._clock += step_s

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
        self._speech_start = 0.0
        self._silence_start = 0.0
        self._clock = 0.0

    def _cut_segment(self, start_s: float, end_s: float) -> dict | None:
        duration = end_s - start_s
        if duration < self._speech_min:
            return None

        sr = self._cfg.sample_rate
        actual_start = max(0.0, start_s - self._pad)
        actual_end = min(self._clock, end_s + self._pad)

        # 映射到 buffer 索引
        buf_start_s = self._clock - len(self._buffer) / sr
        rel_start = int((actual_start - buf_start_s) * sr)
        rel_end = int((actual_end - buf_start_s) * sr)

        rel_start = max(0, rel_start)
        rel_end = min(len(self._buffer), rel_end)

        if rel_end <= rel_start:
            return None

        audio = self._buffer[rel_start:rel_end].copy()
        return {
            "audio": audio,
            "start_ms": start_s * 1000,
            "end_ms": end_s * 1000,
        }
