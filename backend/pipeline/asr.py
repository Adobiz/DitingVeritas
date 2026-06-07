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
    def __init__(self, app_key: str = "", access_key: str = "", access_secret: str = ""):
        self._app_key = app_key
        self._access_key = access_key
        self._access_secret = access_secret

    def configure(self, app_key: str, access_key: str, access_secret: str):
        self._app_key = app_key
        self._access_key = access_key
        self._access_secret = access_secret

    def _get_token(self) -> str:
        try:
            import json
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkcore.request import CommonRequest
            client = AcsClient(self._access_key, self._access_secret, "cn-shanghai")
            request = CommonRequest()
            request.set_method("POST")
            request.set_domain("nls-meta.cn-shanghai.aliyuncs.com")
            request.set_version("2019-02-28")
            request.set_action_name("CreateToken")
            response = client.do_action_with_exception(request)
            return json.loads(response).get("Token", {}).get("Id", "")
        except ImportError:
            logger.error("未安装 aliyun-python-sdk-core，请 pip install aliyun-python-sdk-core")
            return ""
        except Exception as e:
            logger.error(f"获取阿里云 Token 失败: {e}")
            return ""

    def transcribe(self, audio: np.ndarray) -> list[dict]:
        if not self._app_key:
            logger.info("CloudASR: 未配置 app_key")
            return []
        token = self._get_token()
        if not token:
            logger.info("CloudASR: Token 获取失败")
            return []
        logger.info(f"CloudASR: Token 已获取, 开始识别 {len(audio)/16000:.1f}s")
        try:
            import json, threading, time, uuid
            import websocket

            audio_bytes = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            results = []
            done = threading.Event()

            url = f"wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1?token={token}"
            ws = websocket.WebSocketApp(url)

            started = threading.Event()

            def on_open(ws_obj):
                logger.info("CloudASR WS 已连接，发送 StartTranscription…")
                ws_obj.send(json.dumps({
                    "header": {
                        "message_id": str(uuid.uuid4()).replace('-', ''),
                        "task_id": str(uuid.uuid4()).replace('-', ''),
                        "namespace": "SpeechTranscriber",
                        "appkey": self._app_key,
                        "name": "StartTranscription",
                    },
                    "payload": {
                        "format": "pcm",
                        "sample_rate": 16000,
                        "enable_interim_result": True,
                        "enable_punctuation_prediction": True,
                        "enable_voice_detection": False,
                        "max_sentence_silence": 800,
                    },
                    "context": {},
                }))
                # 等待服务器确认后发送音频
                if started.wait(timeout=5):
                    for i in range(0, len(audio_bytes), 3200):
                        ws_obj.send(audio_bytes[i:i+3200], opcode=websocket.ABNF.OPCODE_BINARY)
                ws_obj.send(json.dumps({"header": {
                    "message_id": str(uuid.uuid4()).replace('-', ''), "task_id": _task_id,
                    "appkey": self._app_key,
                    "namespace": "SpeechTranscriber", "name": "StopTranscription",
                }}))

            def on_message(ws_obj, msg):
                logger.info(f"CloudASR raw: {msg[:300]}")
                try:
                    data = json.loads(msg)
                    h = data.get("header", {})
                    name = h.get("name", "")
                    if name == "TaskFailed":
                        logger.error(f"CloudASR TaskFailed: {h.get('status_text','')}")
                        done.set()
                        return
                    if name == "TranscriptionStarted":
                        logger.info("CloudASR: 服务端已就绪，发送音频")
                        started.set()
                        return
                    if name == "TranscriptionResultChanged":
                        started.set()  # 某些版本可能不返回 TranscriptionStarted
                    text = data.get("payload", {}).get("result", "")
                    if name in ("TranscriptionResultChanged", "SentenceEnd") and text:
                        results.append({"text": text.strip(), "start": 0.0, "end": 0.0})
                except Exception as e:
                    logger.error(f"CloudASR msg parse: {e}")

            ws.on_open = on_open
            ws.on_message = on_message
            ws.on_error = lambda ws_obj, err: (logger.error(f"CloudASR WS err: {err}"), done.set())
            ws.on_close = lambda ws_obj, code, reason: (logger.info(f"CloudASR WS close: {code} {reason}"), done.set())

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
        return CloudASR(config.asr_provider.aliyun_app_key,
                        config.asr_provider.aliyun_access_key,
                        config.asr_provider.aliyun_access_secret)
    return LocalASR()


ASREngine = create_asr  # 兼容旧引用（main.py 中 import ASREngine）
