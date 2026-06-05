"""DitingVeritas — 谛听·译真"""
from fastapi import FastAPI

app = FastAPI(title="DitingVeritas", version="0.1.0")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
