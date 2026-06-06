"""faster-whisper 语音识别"""
import logging
import numpy as np
from config import config

logger = logging.getLogger("diting.asr")

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            config.asr.model_size,
            device="cpu",
            compute_type=config.asr.compute_type,
        )
        logger.info(f"faster-whisper 就绪 (size={config.asr.model_size})")
    return _model


class ASREngine:

    def __init__(self):
        self._model = _get_model()
        self._cfg = config.asr

    def transcribe(self, audio: np.ndarray) -> list[dict]:
        # 预处理
        audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio[:, 0]  # 多声道 → 第一通道
        peak = np.abs(audio).max()
        if peak > 0.01:                 # > -40dB 才归一化，避免放大噪声
            audio = audio / peak
        audio = np.clip(audio, -1.0, 1.0)

        if len(audio) < 1600:           # <100ms @16kHz 跳过
            logger.debug("ASR 跳过：音频过短")
            return []

        try:
            segments, _ = self._model.transcribe(
                audio,
                language=self._cfg.language,
                beam_size=self._cfg.beam_size,
                vad_filter=False,
            )
            results = [{"text": s.text.strip(), "start": s.start, "end": s.end}
                       for s in segments if s.text.strip()]
            if results:
                logger.info(f"ASR: {' '.join(r['text'] for r in results)[:80]}")
            else:
                logger.debug("ASR 无输出")
            return results
        except Exception as e:
            logger.error(f"ASR 失败: {e}")
            return []
