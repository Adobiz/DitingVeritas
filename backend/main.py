"""DitingVeritas — 谛听·译真"""
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from models.schemas import (
    ErrorMessage,
    PipelineStatus,
    ServerMessage,
    StatusUpdate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("diting")

app = FastAPI(title="DitingVeritas", version="0.1.0")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/translate")
async def translate_websocket(ws: WebSocket):
    await ws.accept()
    logger.info("客户端已连接")

    await ws.send_json(
        ServerMessage.status(
            StatusUpdate(status=PipelineStatus.IDLE, message="DitingVeritas 已就绪")
        ).model_dump()
    )

    try:
        async for raw in ws.iter_text():
            try:
                data = json.loads(raw)
                logger.info(f"收到: {data.get('type')}")
            except json.JSONDecodeError:
                await ws.send_json(
                    ServerMessage.error(
                        ErrorMessage(code="INVALID_JSON", message="无法解析 JSON")
                    ).model_dump()
                )
    except WebSocketDisconnect:
        logger.info("客户端断开连接")
    finally:
        logger.info("WebSocket 连接关闭")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
