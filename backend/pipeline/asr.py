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
            config.asr.model_size, device="cpu",
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
    def __init__(self, app_key: str = "", token: str = ""):
        self._app_key = app_key
        self._token = token

    def configure(self, app_key: str, token: str):
        self._app_key = app_key
        self._token = token

    def transcribe(self, audio: np.ndarray) -> list[dict]:
        if not self._app_key or not self._token:
            return []
        try:
            import json, threading, time
            import websocket

            audio_bytes = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            results = []
            done = threading.Event()

            url = f"wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1?token={self._token}"
            ws = websocket.WebSocketApp(url)

            def on_open(ws_obj):
                ws_obj.send(json.dumps({
                    "header": {
                        "message_id": f"m_{int(time.time()*1000)}",
                        "task_id": f"t_{int(time.time()*1000)}",
                        "namespace": "SpeechTranscriber",
                        "name": "StartTranscription",
                        "appkey": self._app_key,
                    },
                    "payload": {"format": "pcm", "sample_rate": 16000,
                                "enable_interim_result": True,
                                "enable_punctuation_prediction": True},
                }))
                for i in range(0, len(audio_bytes), 3200):
                    ws_obj.send(audio_bytes[i:i+3200], opcode=websocket.ABNF.OPCODE_BINARY)
                ws_obj.send(json.dumps({"header": {
                    "message_id": "stop", "task_id": "stop",
                    "namespace": "SpeechTranscriber", "name": "StopTranscription",
                    "appkey": self._app_key,
                }}))

            def on_message(ws_obj, msg):
                try:
                    data = json.loads(msg)
                    name = data.get("header", {}).get("name", "")
                    text = data.get("payload", {}).get("result", "")
                    if name in ("TranscriptionResultChanged", "SentenceEnd") and text:
                        results.append({"text": text.strip(), "start": 0.0, "end": 0.0})
                except Exception:
                    pass

            t = threading.Thread(target=ws.run_forever)
            t.start()
            done.wait(timeout=10)
            ws.close()
            t.join(timeout=2)

            if results:
                logger.info(f"ASR(cloud): {' '.join(r['text'] for r in results)[:80]}")
            return results
        except ImportError:
            logger.error("未安装 websocket-client")
            return []
        except Exception as e:
            logger.error(f"CloudASR 失败: {e}")
            return []


# ── 工厂 ────────────────────────────────────────


def create_asr(provider: str = "") -> ASRBackend:
    p = provider or config.asr_provider.provider
    if p == "cloud":
        return CloudASR(config.asr_provider.aliyun_app_key, config.asr_provider.aliyun_token)
    return LocalASR()


ASREngine = create_asr  # 兼容旧引用（main.py 中 import ASREngine）
