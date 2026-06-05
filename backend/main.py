"""DitingVeritas 谛听 译真"""
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from models.schemas import (
    ContextUpdate,
    ErrorMessage,
    MessageType,
    PipelineStatus,
    ServerMessage,
    StartRequest,
    StatusUpdate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("diting")

app = FastAPI(title="DitingVeritas", version="0.1.0")


class PipelineState:
    def __init__(self):
        self.status = PipelineStatus.IDLE
        self.source_lang = "en"
        self.target_lang = "zh"
        self.context: ContextUpdate | None = None

    def can_start(self) -> bool: return self.status in (PipelineStatus.IDLE, PipelineStatus.ERROR)
    def can_stop(self) -> bool:  return self.status in (PipelineStatus.RUNNING, PipelineStatus.PAUSED)
    def can_pause(self) -> bool: return self.status == PipelineStatus.RUNNING
    def can_resume(self) -> bool: return self.status == PipelineStatus.PAUSED


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/translate")
async def translate_websocket(ws: WebSocket):
    await ws.accept()
    logger.info("客户端已连接")
    state = PipelineState()

    await ws.send_json(
        ServerMessage.status(
            StatusUpdate(status=PipelineStatus.IDLE, message="DitingVeritas 已就绪")
        ).model_dump()
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
                    ServerMessage.error(ErrorMessage(code="MISSING_TYPE", message="缺少 type 字段")).model_dump()
                )
                continue

            # ── 消息路由 ──────────────────────────

            if msg_type == MessageType.START:
                if not state.can_start():
                    await ws.send_json(
                        ServerMessage.error(ErrorMessage(code="INVALID_STATE", message=f"当前状态 {state.status} 无法启动")).model_dump()
                    )
                    continue
                try:
                    req = StartRequest(**data)
                except Exception as e:
                    await ws.send_json(
                        ServerMessage.error(ErrorMessage(code="INVALID_PAYLOAD", message=str(e))).model_dump()
                    )
                    continue

                state.source_lang = req.source_lang
                state.target_lang = req.target_lang
                if req.context:
                    state.context = req.context
                state.status = PipelineStatus.RUNNING
                await ws.send_json(
                    ServerMessage.status(StatusUpdate(status=PipelineStatus.RUNNING, message="管道已启动")).model_dump()
                )

            elif msg_type == MessageType.STOP:
                if not state.can_stop():
                    await ws.send_json(
                        ServerMessage.error(ErrorMessage(code="INVALID_STATE", message=f"当前状态 {state.status} 无法停止")).model_dump()
                    )
                    continue
                state.status = PipelineStatus.IDLE
                await ws.send_json(
                    ServerMessage.status(StatusUpdate(status=PipelineStatus.IDLE, message="管道已停止")).model_dump()
                )

            elif msg_type == MessageType.PAUSE:
                if not state.can_pause():
                    await ws.send_json(
                        ServerMessage.error(ErrorMessage(code="INVALID_STATE", message=f"当前状态 {state.status} 无法暂停")).model_dump()
                    )
                    continue
                state.status = PipelineStatus.PAUSED
                await ws.send_json(
                    ServerMessage.status(StatusUpdate(status=PipelineStatus.PAUSED, message="管道已暂停")).model_dump()
                )

            elif msg_type == MessageType.RESUME:
                if not state.can_resume():
                    await ws.send_json(
                        ServerMessage.error(ErrorMessage(code="INVALID_STATE", message=f"当前状态 {state.status} 无法恢复")).model_dump()
                    )
                    continue
                state.status = PipelineStatus.RUNNING
                await ws.send_json(
                    ServerMessage.status(StatusUpdate(status=PipelineStatus.RUNNING, message="管道已恢复")).model_dump()
                )

            elif msg_type == MessageType.CONTEXT_UPDATE:
                try:
                    state.context = ContextUpdate(**data)
                except Exception as e:
                    await ws.send_json(
                        ServerMessage.error(ErrorMessage(code="INVALID_PAYLOAD", message=str(e))).model_dump()
                    )
                    continue
                await ws.send_json(
                    ServerMessage.status(StatusUpdate(status=state.status, message="语境已记录")).model_dump()
                )

            else:
                await ws.send_json(
                    ServerMessage.error(ErrorMessage(code="UNKNOWN_TYPE", message=f"未知消息: {msg_type}")).model_dump()
                )

    except WebSocketDisconnect:
        logger.info("客户端断开连接")
    finally:
        state.status = PipelineStatus.IDLE
        logger.info("WebSocket 连接关闭")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
