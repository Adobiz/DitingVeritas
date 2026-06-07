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
from pipeline.modes import get_mode
from pipeline.incremental import IncrementalProcessor
from pipeline.context_loader import load_context, build_context_block

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("diting")
app = FastAPI(title="DitingVeritas", version="0.5.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TranslationPipeline:

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
        self._interim_seq = 0
        self._interim_tl_task: asyncio.Task | None = None
        self._infer_task: asyncio.Task | None = None
        self._last_infer_text = ""
        self._last_tl_text = ""
        self._incr = IncrementalProcessor()
        self._confirmed_tl = ""
        self._tl_lock = asyncio.Lock()

    async def start(self, req: StartRequest | None = None):
        if self.status == PipelineStatus.RUNNING:
            return
        if req:
            self.source_lang = req.source_lang
            self.target_lang = req.target_lang
            config.asr.language = req.source_lang  # 同步到 ASR 和翻译
            if req.context: self.context = req.context
        ctx = load_context(self.context)
        self._translator.context_block = build_context_block(ctx)
        self.status = PipelineStatus.STARTING
        if ctx:
            await self._push_status(f"语境已加载: {ctx.topic[:30]}")
        else:
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
            try: await self._task
            except asyncio.CancelledError: pass
        self._drain()
        for t in [self._interim_tl_task, self._infer_task]:
            if t and not t.done(): t.cancel()
        self._translator.context_block = ""  # 清除语境
        self.status = PipelineStatus.IDLE
        await self._push_status("管道已停止")

    def _on_chunk(self, audio: np.ndarray, rms: float):
        if self.status != PipelineStatus.RUNNING: return
        try: self._queue.put_nowait((audio.copy(), rms))
        except asyncio.QueueFull: pass

    def _drain(self):
        while not self._queue.empty():
            try: self._queue.get_nowait()
            except asyncio.QueueEmpty: break

    class _IncASR:
        """增量 ASR：只返回新增文本（不重复）"""
        def __init__(self, asr, loop):
            self._a, self._l, self._last = asr, loop, ""
        async def delta(self, audio):
            try: results = await self._l.run_in_executor(None, self._a.transcribe, audio)
            except Exception: return ""
            text = " ".join(r["text"] for r in results).strip()
            if not text: return ""
            if text.startswith(self._last):
                d = text[len(self._last):].strip(); self._last = text; return d
            self._last = text; return text  # 修正→整句

    # ── 纯 ASR（不翻译）──────────────────────

    async def _infer_only(self, loop, audio: np.ndarray) -> str | None:
        try:
            results = await loop.run_in_executor(None, self._asr.transcribe, audio)
            if not results: return None
            text = " ".join(r["text"] for r in results)
            return text.strip() or None
        except Exception as e:
            logger.debug(f"ASR 推理异常: {e}")
            return None

    async def _tl_delta(self, delta_src: str, mode, seq_id: int, full_src: str):
        """增量翻译：只翻新增文本"""
        if not delta_src: return
        await asyncio.sleep(mode.translate_debounce_ms / 1000.0)
        if seq_id != self._interim_seq: return
        try:
            accumulated = ""
            gen = self._translator.translate_stream_async(delta_src)
            async for token in gen:
                accumulated += token
                await self._send(ServerMessage.translation(
                    TranslationResult(source_text=full_src,
                                      translation=self._confirmed_tl + accumulated,
                                      is_partial=True)))
            self._confirmed_tl += accumulated
            await self._send(ServerMessage.translation(
                TranslationResult(source_text=full_src,
                                  translation=self._confirmed_tl,
                                  is_partial=False)))
        except Exception as e:
            logger.debug(f"增量翻译异常: {e}")

    # ── 独立翻译任务 ─────────────────────────

    async def _tl_stream(self, text: str, mode, seq_id: int, loop):
        if not text: return
        await asyncio.sleep(mode.translate_debounce_ms / 1000.0)
        if seq_id != self._interim_seq: return
        if text == self._last_tl_text: return
        async with self._tl_lock:
            try:
                accumulated = ""
                gen = self._translator.translate_stream_async(text)
                async for token in gen:
                    accumulated += token
                    await self._send(ServerMessage.translation(
                        TranslationResult(source_text=text, translation=accumulated, is_partial=True)))
                if accumulated:
                    self._last_tl_text = text
                    await self._send(ServerMessage.translation(
                        TranslationResult(source_text=text, translation=accumulated, is_partial=False)))
            except Exception as e:
                logger.debug(f"翻译异常: {e}")

    async def _run_stable(self, loop, mode):
        """稳定：后台低频缓存 ASR，final 直接翻译"""
        from time import monotonic as _clock
        buf = []
        last_asr = 0.0
        max_s = int(mode.asr_buffer_sec * 16000)

        while self.status == PipelineStatus.RUNNING:
            try: chunk, rms = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError: continue
            if self.status != PipelineStatus.RUNNING: break
            try: segments = self._vad.process(chunk)
            except Exception: continue

            if self._vad.is_speaking:
                buf.append(chunk)
                while sum(len(c) for c in buf) > max_s and len(buf) > 1: buf.pop(0)

            for seg in segments:
                audio = seg.get("audio")
                if audio is None or len(audio) == 0: continue
                buf = []
                if len(audio) > max_s: audio = audio[-max_s:]
                try: results = await loop.run_in_executor(None, self._asr.transcribe, audio)
                except Exception: continue
                if not results: continue
                text = " ".join(r["text"] for r in results)
                logger.info(f"ASR(final): {text[:80]}")
                try: t = await self._translator.translate_async(text)
                except Exception: t = text
                await self._send(ServerMessage.translation(
                    TranslationResult(source_text=text, translation=t or text, is_partial=False)))

    async def _run(self):
        loop = asyncio.get_running_loop()
        mode_name = getattr(config, "pipeline_mode", "balanced") or "balanced"
        mode = get_mode(mode_name)
        if mode_name == "stable":
            await self._run_stable(loop, mode)
            return
        logger.info(f"模式: {mode.label} (int={mode.asr_interval}s buf={mode.asr_buffer_sec}s sil={mode.vad_silence_ms}ms)")

        from time import monotonic as _clock
        buf, last_infer, seq = [], 0.0, 0
        pending, last_quality = [], None
        max_s = int(mode.asr_buffer_sec * 16000)
        min_s = int(0.3 * 16000)

        async def _tl_final(src: str, s: int):
            self._incr.finalize(src)
            self._confirmed_tl = ""
            try: t = await self._translator.translate_async(src)
            except Exception: t = src
            await self._send(ServerMessage.translation(
                TranslationResult(source_text=src, translation=t or src, is_partial=False, segment_id=str(s))))

        while self.status == PipelineStatus.RUNNING:
            try:
                chunk, rms = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if self.status != PipelineStatus.RUNNING: break

            try: segments = self._vad.process(chunk)
            except Exception: continue

            # ── 流式 buffer ──
            if self._vad.is_speaking:
                buf.append(chunk)
                total = sum(len(c) for c in buf)
                while total > max_s and len(buf) > 1:
                    total -= len(buf[0]); buf.pop(0)

                now = _clock()
                if now - last_infer >= mode.asr_interval:
                    if self._infer_task and not self._infer_task.done():
                        if mode.drop_stale: continue
                        self._infer_task.cancel()  # 直接取消，不等待

                    audio = np.concatenate(buf)
                    if len(audio) >= min_s:
                        last_infer = now  # 成功启动才刷新
                        self._infer_task = asyncio.create_task(
                            self._infer_only(loop, audio[-max_s:]))

            # ── ASR 完成 ──
            if self._infer_task and self._infer_task.done():
                try: text = self._infer_task.result()
                except Exception: text = None
                self._infer_task = None
                if text and isinstance(text, str) and text.strip():
                    logger.debug(f"ASR: {text[:60]}")
                    if mode_name == "stable":
                        self._incr.process(text)  # 后台预热，不发前端
                    elif mode.show_interim:
                        if mode_name == "turbo":
                            # 极简路径：直接发原文 + 异步翻译
                            await self._send(ServerMessage.translation(
                                TranslationResult(source_text=text, translation="", is_partial=True)))
                            self._interim_seq += 1
                            if self._interim_tl_task and not self._interim_tl_task.done():
                                self._interim_tl_task.cancel()
                            self._interim_tl_task = asyncio.create_task(
                                self._tl_stream(text, mode, self._interim_seq, loop))
                        else:
                            # 均衡/稳定：增量 diff
                            delta = self._incr.process(text)
                            if delta:
                                self._interim_seq += 1
                                if self._interim_tl_task and not self._interim_tl_task.done() and mode.drop_stale:
                                    self._interim_tl_task.cancel()
                                if delta["type"] == "append":
                                    self._interim_tl_task = asyncio.create_task(
                                        self._tl_delta(delta["delta"], mode, self._interim_seq, delta["full"]))
                                elif delta["type"] == "correct":
                                    self._confirmed_tl = ""
                                    self._interim_tl_task = asyncio.create_task(
                                        self._tl_delta(delta["delta"], mode, self._interim_seq, delta["full"]))


            # ── VAD final ──
            for seg in segments:
                audio = seg.get("audio")
                if audio is None or len(audio) == 0: continue
                buf = []
                if len(audio) > max_s: audio = audio[-max_s:]
                try: results = await loop.run_in_executor(None, self._asr.transcribe, audio)
                except Exception: continue
                if not results: continue
                text = " ".join(r["text"] for r in results)
                logger.info(f"ASR(final): {text[:80]}")
                seq += 1

                words = text.split()
                if len(words) < mode.min_words:
                    pending.append(text)
                    if len(pending) >= 3:
                        batch = " ".join(pending); pending = []
                        asyncio.create_task(_tl_final(batch, seq))
                else:
                    if pending: text = " ".join(pending + [text]); pending = []
                    asyncio.create_task(_tl_final(text, seq))
                self._last_infer_text = ""
                self._last_tl_text = ""

            quality = self._rms_quality(rms)
            if quality != last_quality:
                last_quality = quality
                await self._send(ServerMessage.status(
                    StatusUpdate(status=PipelineStatus.RUNNING, message="", audio_quality=quality)))

    @staticmethod
    def _rms_quality(rms: float) -> AudioQuality:
        if rms < 0.001: return AudioQuality.SILENCE
        if rms < 0.05: return AudioQuality.GOOD
        return AudioQuality.NOISY

    async def _send(self, msg: ServerMessage):
        try: await self._ws.send_json(msg.model_dump())
        except Exception: pass

    async def _push_status(self, message: str):
        await self._send(ServerMessage.status(StatusUpdate(status=self.status, message=message)))


class PipelineState:
    def __init__(self): self.status = PipelineStatus.IDLE
    def can_start(self) -> bool: return self.status in (PipelineStatus.IDLE, PipelineStatus.ERROR)
    def can_stop(self) -> bool: return self.status == PipelineStatus.RUNNING


@app.websocket("/ws/translate")
async def translate_websocket(ws: WebSocket):
    await ws.accept()
    logger.info("客户端已连接")
    state = PipelineState()
    pipeline: TranslationPipeline | None = None
    await ws.send_json(ServerMessage.status(StatusUpdate(status=PipelineStatus.IDLE, message="已就绪")).model_dump())

    try:
        async for raw in ws.iter_text():
            try: data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json(ServerMessage.error(ErrorMessage(code="INVALID_JSON", message="无法解析 JSON")).model_dump()); continue
            msg_type = data.get("type")
            if not msg_type:
                await ws.send_json(ServerMessage.error(ErrorMessage(code="MISSING_TYPE", message="缺少 type")).model_dump()); continue

            if msg_type == MessageType.START:
                if not state.can_start():
                    await ws.send_json(ServerMessage.error(ErrorMessage(code="INVALID_STATE", message="无法启动")).model_dump()); continue
                try: req = StartRequest(**data)
                except Exception as e:
                    await ws.send_json(ServerMessage.error(ErrorMessage(code="INVALID_PAYLOAD", message=str(e))).model_dump()); continue
                dev_id = data.get("device_index")
                if dev_id is not None: config.audio.device_index = int(dev_id)
                if data.get("api_key"): config.translator.openai_api_key = data["api_key"]
                if data.get("api_base_url"): config.translator.openai_base_url = data["api_base_url"]
                if data.get("model"): config.translator.model = data["model"]
                if data.get("local_path"): config.translator.local_path = data["local_path"]
                if data.get("pipeline_mode"): config.pipeline_mode = data["pipeline_mode"]
                if data.get("gpu"):
                    import torch
                    if torch.cuda.is_available():
                        config.asr.device = "cuda"
                        config.asr.compute_type = "float16"
                    else:
                        config.asr.device = "cpu"
                        config.asr.compute_type = "int8"
                else:
                    config.asr.device = "cpu"
                    config.asr.compute_type = "int8"
                pipeline = TranslationPipeline(ws)
                await pipeline.start(req)
                state.status = PipelineStatus.RUNNING

            elif msg_type == MessageType.STOP:
                if pipeline: await pipeline.stop(); pipeline = None
                state.status = PipelineStatus.IDLE

            elif msg_type == MessageType.CONTEXT_UPDATE:
                if pipeline:
                    try: pipeline.context = ContextUpdate(**data)
                    except Exception: pass
                    ctx = load_context(pipeline.context)
                    pipeline._translator.context_block = build_context_block(ctx)
                    detail = f"语境已更新: {ctx.topic[:30]}" if ctx and ctx.topic else "语境已更新"
                    await ws.send_json(ServerMessage.status(StatusUpdate(status=state.status, message=detail)).model_dump())

            else:
                await ws.send_json(ServerMessage.error(ErrorMessage(code="UNKNOWN_TYPE", message=str(msg_type))).model_dump())

    except WebSocketDisconnect: logger.info("客户端断开")
    finally:
        if pipeline: await pipeline.stop()


@app.get("/api/health")
async def health(): return {"status": "ok"}


@app.get("/api/gpu")
async def gpu_status():
    try:
        import torch
        cuda = torch.cuda.is_available()
        return {"cuda": cuda, "device": "cuda" if cuda else "cpu"}
    except Exception:
        return {"cuda": False, "device": "cpu"}


@app.get("/api/devices")
async def list_devices():
    from pipeline.audio_capture import AudioCapture
    return AudioCapture().list_devices()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
