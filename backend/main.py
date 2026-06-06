"""DitingVeritas — 谛听·译真"""
import asyncio
import json
import logging

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from config import config
from models.schemas import (
    AudioQuality,
    ContextUpdate,
    ErrorMessage,
    MessageType,
    PipelineStatus,
    ServerMessage,
    StartRequest,
    StatusUpdate,
    TranslationResult,
)
from pipeline.audio_capture import AudioCapture
from pipeline.vad import VoiceActivityDetector
from pipeline.asr import ASREngine
from pipeline.translator import create_translator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("diting")
app = FastAPI(title="DitingVeritas", version="0.2.0")


class TranslationPipeline:
    """管道编排器：Audio → VAD → ASR → WebSocket"""

    def __init__(self, ws: WebSocket):
        self._ws = ws
        self.status = PipelineStatus.IDLE
        self._audio = AudioCapture()
        self._vad = VoiceActivityDetector()
        self._asr = ASREngine()
        self._translator = create_translator()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._task: asyncio.Task | None = None
        self.source_lang = "en"
        self.target_lang = "zh"
        self.context: ContextUpdate | None = None

    # ── 生命周期 ──────────────────────────────

    async def start(self, req: StartRequest | None = None):
        if self.status == PipelineStatus.RUNNING:
            return
        if req:
            self.source_lang = req.source_lang
            self.target_lang = req.target_lang
            if req.context:
                self.context = req.context

        self.status = PipelineStatus.STARTING
        await self._push_status("管道启动中…")
        self._vad.reset()
        self._audio.start(self._on_chunk)
        self._task = asyncio.create_task(self._run())
        self.status = PipelineStatus.RUNNING
        await self._push_status("管道已启动")

    async def stop(self):
        if self.status == PipelineStatus.IDLE:
            return
        self.status = PipelineStatus.STOPPING
        await self._push_status("管道停止中…")
        self._audio.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self.status = PipelineStatus.IDLE
        await self._push_status("管道已停止")

    # ── 音频回调（sounddevice 线程）───────────

    def _on_chunk(self, audio: np.ndarray, rms: float):
        if self.status != PipelineStatus.RUNNING:
            return
        try:
            self._queue.put_nowait((audio.copy(), rms))
        except asyncio.QueueFull:
            pass

    # ── 处理循环（asyncio）─────────────────────

    async def _run(self):
        loop = asyncio.get_running_loop()
        last_quality = None

        while self.status == PipelineStatus.RUNNING:
            try:
                chunk, rms = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if self.status != PipelineStatus.RUNNING:
                break

            # VAD 切句
            try:
                segments = self._vad.process(chunk)
            except Exception as e:
                logger.error(f"VAD 异常: {e}")
                continue

            for seg in segments:
                # ASR（线程池异步执行）
                try:
                    results = await loop.run_in_executor(None, self._asr.transcribe, seg["audio"])
                except Exception as e:
                    logger.error(f"ASR 异常: {e}")
                    continue

                if not results:
                    continue

                text = " ".join(r["text"] for r in results)
                logger.info(f"ASR: {text[:80]}")

                translation = await self._translator.translate_async(text)
                if translation != text:
                    logger.info(f"翻译: {translation[:50]}")
                else:
                    logger.warning("翻译回退原文，请检查 API key 或网络")

                await self._send(ServerMessage.translation(
                    TranslationResult(source_text=text, translation=translation, is_partial=False)
                ))

            # 音频质量推送
            quality = self._rms_quality(rms)
            if quality != last_quality:
                last_quality = quality
                await self._send(ServerMessage.status(
                    StatusUpdate(status=PipelineStatus.RUNNING, message="", audio_quality=quality)
                ))

    # ── 辅助 ──────────────────────────────────

    @staticmethod
    def _rms_quality(rms: float) -> AudioQuality:
        if rms < 0.001:
            return AudioQuality.SILENCE
        if rms < 0.05:
            return AudioQuality.GOOD
        return AudioQuality.NOISY

    async def _send(self, msg: ServerMessage):
        try:
            await self._ws.send_json(msg.model_dump())
        except Exception:
            pass

    async def _push_status(self, message: str):
        await self._send(ServerMessage.status(StatusUpdate(status=self.status, message=message)))


# ── WebSocket 端点 ──────────────────────────────


class PipelineState:
    def __init__(self):
        self.status = PipelineStatus.IDLE

    def can_start(self) -> bool: return self.status in (PipelineStatus.IDLE, PipelineStatus.ERROR)
    def can_stop(self) -> bool:  return self.status == PipelineStatus.RUNNING


@app.websocket("/ws/translate")
async def translate_websocket(ws: WebSocket):
    await ws.accept()
    logger.info("客户端已连接")
    state = PipelineState()
    pipeline: TranslationPipeline | None = None

    await ws.send_json(
        ServerMessage.status(StatusUpdate(status=PipelineStatus.IDLE, message="已就绪")).model_dump()
    )

    try:
        async for raw in ws.iter_text():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json(
                    ServerMessage.error(ErrorMessage(code="INVALID_JSON", message="无法解析 JSON")).model_dump()
                )
                continue

            msg_type = data.get("type")
            if not msg_type:
                await ws.send_json(
                    ServerMessage.error(ErrorMessage(code="MISSING_TYPE", message="缺少 type")).model_dump()
                )
                continue

            if msg_type == MessageType.START:
                if not state.can_start():
                    await ws.send_json(
                        ServerMessage.error(ErrorMessage(code="INVALID_STATE", message="无法启动")).model_dump()
                    )
                    continue
                try:
                    req = StartRequest(**data)
                except Exception as e:
                    await ws.send_json(
                        ServerMessage.error(ErrorMessage(code="INVALID_PAYLOAD", message=str(e))).model_dump()
                    )
                    continue
                pipeline = TranslationPipeline(ws)
                await pipeline.start(req)
                state.status = PipelineStatus.RUNNING

            elif msg_type == MessageType.STOP:
                if pipeline:
                    await pipeline.stop()
                    pipeline = None
                state.status = PipelineStatus.IDLE

            elif msg_type == MessageType.CONTEXT_UPDATE:
                if pipeline:
                    try:
                        pipeline.context = ContextUpdate(**data)
                    except Exception:
                        pass
                await ws.send_json(
                    ServerMessage.status(StatusUpdate(status=state.status, message="语境已更新")).model_dump()
                )

            else:
                await ws.send_json(
                    ServerMessage.error(ErrorMessage(code="UNKNOWN_TYPE", message=str(msg_type))).model_dump()
                )

    except WebSocketDisconnect:
        logger.info("客户端断开")
    finally:
        if pipeline:
            await pipeline.stop()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
