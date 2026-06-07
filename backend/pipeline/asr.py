"""语音识别 — 可替换后端（本地 / 云端）"""
import logging
from abc import ABC, abstractmethod

import numpy as np

from config import config

logger = logging.getLogger("diting.asr")


class ASRBackend(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> list[dict]:
        ...


# ── 本地后端：faster-whisper ────────────────────

_local_model = None


def _get_local_model():
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel
        _local_model = WhisperModel(
            config.asr.model_size, device=config.asr.device,
            compute_type=config.asr.compute_type,
        )
        logger.info(f"faster-whisper 就绪 (size={config.asr.model_size})")
    return _local_model


class LocalASR(ASRBackend):
    def __init__(self):
        self._model = _get_local_model()
        self._cfg = config.asr

    def transcribe(self, audio: np.ndarray) -> list[dict]:
        audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio[:, 0]
        peak = np.abs(audio).max()
        if peak > 0.01:
            audio = audio / peak
        audio = np.clip(audio, -1.0, 1.0)
        if len(audio) < 1600:
            return []
        try:
            segments, _ = self._model.transcribe(
                audio, language=self._cfg.language,
                beam_size=self._cfg.beam_size, vad_filter=False,
            )
            results = [{"text": s.text.strip(), "start": s.start, "end": s.end}
                       for s in segments if s.text.strip()]
            if results:
                logger.info(f"ASR(local): {' '.join(r['text'] for r in results)[:80]}")
            return results
        except Exception as e:
            logger.error(f"ASR(local) 失败: {e}")
            return []


# ── 云端后端：阿里云实时 ASR ────────────────────

class CloudASR(ASRBackend):
    """阿里云实时 ASR — 需配置后使用"""

    def __init__(self, app_key: str = ""):
        self._app_key = app_key

    def transcribe(self, audio: np.ndarray) -> list[dict]:
        if not self._app_key:
            return []
        logger.warning("CloudASR: WebSocket 模式待完善，请使用 LocalASR")
        return []


# ── 工厂 ────────────────────────────────────────


def create_asr(provider: str = "") -> ASRBackend:
    p = provider or config.asr_provider.provider
    if p == "cloud":
        return CloudASR(config.asr_provider.aliyun_app_key)
    return LocalASR()


ASREngine = create_asr  # 兼容旧引用（main.py 中 import ASREngine）
