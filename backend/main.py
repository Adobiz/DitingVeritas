"""DitingVeritas — 谛听·译真"""
import asyncio
import json
import logging

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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
app = FastAPI(title="DitingVeritas", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
        mode = getattr(config, "pipeline_mode", "balanced") or "balanced"
        if mode == "stable":
            await self._run_stable()
            return
        if mode == "turbo":
            await self._run_turbo()
            return
        await self._run_balanced()

    async def _run_stable(self):
        """稳定模式：无 partial，VAD 切句 → ASR → 同步翻译 → 发送"""
        loop = asyncio.get_running_loop()
        while self.status == PipelineStatus.RUNNING:
            try:
                chunk, rms = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if self.status != PipelineStatus.RUNNING: break
            try:
                segments = self._vad.process(chunk)
            except Exception as e:
                logger.error(f"VAD: {e}"); continue
            for seg in segments:
                audio = seg.get("audio")
                if audio is None or len(audio) == 0: continue
                try:
                    results = await loop.run_in_executor(None, self._asr.transcribe, audio[:6*16000])
                except Exception: continue
                if not results: continue
                text = " ".join(r["text"] for r in results)
                logger.info(f"ASR: {text[:80]}")
                t = await self._translator.translate_async(text)
                await self._send(ServerMessage.translation(
                    TranslationResult(source_text=text, translation=t or text, is_partial=False)))
            quality = self._rms_quality(rms)
            if quality != getattr(self, '_last_q', None):
                self._last_q = quality
                await self._send(ServerMessage.status(StatusUpdate(status=PipelineStatus.RUNNING, message="", audio_quality=quality)))

    async def _run_turbo(self):
        """强化模式：buffer 每 0.5s 全量推理 partial + Simul 增量翻译"""
        loop = asyncio.get_running_loop()
        buf = []
        last_infer = 0.0
        _last = ""
        _task = None
        from time import monotonic as _clock
        while self.status == PipelineStatus.RUNNING:
            try:
                chunk, rms = await asyncio.wait_for(self._queue.get(), timeout=0.3)
            except asyncio.TimeoutError:
                continue
            if self.status != PipelineStatus.RUNNING: break
            buf.append(chunk)
            buf = buf[-90:]  # 保留最近 ~6s
            now = _clock()
            if now - last_infer < 0.5: continue
            if _task and not _task.done(): continue  # 推理堆积跳过
            audio = np.concatenate(buf)[-6*16000:]
            last_infer = now
            _task = asyncio.create_task(self._turbo_infer(loop, audio, _last))
        if _task: await _task

    async def _turbo_infer(self, loop, audio, last_text):
        try:
            results = await loop.run_in_executor(None, self._asr.transcribe, audio)
            text = " ".join(r["text"] for r in results)
            if not text or text == last_text: return last_text
            logger.info(f"ASR(turbo): {text[:80]}")
            await self._send(ServerMessage.translation(
                TranslationResult(source_text=text, translation="", is_partial=True)))
            t = await self._translator.translate_async(text)
            if t and t != text:
                await self._send(ServerMessage.translation(
                    TranslationResult(source_text=text, translation=t, is_partial=True)))
            return text
        except Exception: return last_text

    async def _run_balanced(self):
        """均衡模式：partial 每 2s + VAD final + 反压翻译"""
        loop = asyncio.get_running_loop()
        last_quality = None
        from time import monotonic as _clock
        speech_buf = []
        last_partial = 0.0
        INTERVAL = 2.0
        seq = 0
        _latest_text = ""
        _translate_task = None
        pending = []

        async def _fire_translate(src: str, s: int, partial: bool):
            """反压翻译：只译最新文本，旧任务自动取消"""
            nonlocal _latest_text, _translate_task
            if src == _latest_text:
                return
            _latest_text = src
            if _translate_task and not _translate_task.done():
                _translate_task.cancel()
            _translate_task = asyncio.create_task(_do_translate(src, s, partial))

        async def _do_translate(src: str, s: int, partial: bool):
            await self._send(ServerMessage.translation(
                TranslationResult(source_text=src, translation="", is_partial=True,
                                  segment_id=str(s))))
            if partial:
                return  # partial 不翻译，只推原文
            try:
                t = await self._translator.translate_async(src)
            except asyncio.CancelledError:
                return
            except Exception:
                t = src
            if t != src:
                logger.info(f"翻译: {t[:50]}")
            await self._send(ServerMessage.translation(
                TranslationResult(source_text=src, translation=t, is_partial=False,
                                  segment_id=str(s))))

        while self.status == PipelineStatus.RUNNING:
            try:
                chunk, rms = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if self.status != PipelineStatus.RUNNING:
                break

            # VAD
            try:
                segments = self._vad.process(chunk)
            except Exception as e:
                logger.error(f"VAD 异常: {e}")
                continue

            # ── 流式 partial：说话中每 2s 推原文 ──
            if self._vad.is_speaking:
                speech_buf.append(chunk)
                now = _clock()
                if now - last_partial >= INTERVAL:
                    last_partial = now
                    total = np.concatenate(speech_buf)
                    win = total[-6*16000:] if len(total) > 6*16000 else total
                    try:
                        results = await loop.run_in_executor(None, self._asr.transcribe, win)
                    except Exception:
                        continue
                    if results:
                        text = " ".join(r["text"] for r in results)
                        seq += 1
                        logger.debug(f"ASR(partial): {text[:60]}")
                        await self._send(ServerMessage.translation(
                            TranslationResult(source_text=text, translation="", is_partial=True,
                                              segment_id=str(seq))))
            else:
                speech_buf = []
                last_partial = 0.0

            # ── VAD 切句 → final + 翻译 ──
            for seg in segments:
                audio = seg.get("audio")
                if audio is None or len(audio) == 0:
                    continue
                max_samples = 6 * 16000
                if len(audio) > max_samples:
                    audio = audio[-max_samples:]
                try:
                    results = await loop.run_in_executor(None, self._asr.transcribe, audio)
                except Exception as e:
                    logger.error(f"ASR 异常: {e}")
                    continue
                if not results:
                    continue

                text = " ".join(r["text"] for r in results)
                logger.info(f"ASR(final): {text[:80]}")
                seq += 1
                speech_buf = []
                last_partial = _clock()

                # 短句攒批
                if len(text.split()) < 5:
                    pending.append(text)
                    if len(pending) >= 3:
                        batch = " ".join(pending)
                        pending = []
                        asyncio.create_task(_fire_translate(batch, seq, False))
                else:
                    if pending:
                        text = " ".join(pending + [text])
                        pending = []
                    asyncio.create_task(_fire_translate(text, seq, False))

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
                dev_id = data.get("device_index")
                if dev_id is not None:
                    config.audio.device_index = int(dev_id)
                # 前端传入的模型配置
                if data.get("api_key"):
                    config.translator.openai_api_key = data["api_key"]
                if data.get("api_base_url"):
                    config.translator.openai_base_url = data["api_base_url"]
                if data.get("model"):
                    config.translator.model = data["model"]
                if data.get("pipeline_mode"):
                    config.pipeline_mode = data["pipeline_mode"]
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


@app.get("/api/devices")
async def list_devices():
    from pipeline.audio_capture import AudioCapture
    return AudioCapture().list_devices()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
