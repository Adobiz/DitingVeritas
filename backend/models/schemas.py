"""消息协议"""
import time
import uuid
from enum import Enum
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    START = "start"
    STOP = "stop"
    CONTEXT_UPDATE = "context_update"


class OutputType(str, Enum):
    TRANSLATION = "translation"
    CORRECTION = "correction"
    STATUS = "status"
    ERROR = "error"
    CONTEXT_READY = "context_ready"


class PipelineStatus(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class AudioQuality(str, Enum):
    GOOD = "good"
    NOISY = "noisy"
    SILENCE = "silence"


class ContextUpdate(BaseModel):
    url: str | None = None
    title: str | None = None
    keywords: str | None = None


class StartRequest(BaseModel):
    source_lang: str = "en"
    target_lang: str = "zh"
    context: ContextUpdate | None = None


# ── 服务端 → 客户端 ──────────────────────────────


class TranslationResult(BaseModel):
    segment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_text: str
    translation: str
    is_partial: bool = False
    timestamp: float = Field(default_factory=time.time)


class CorrectionResult(BaseModel):
    segment_id: str
    old_translation: str
    new_translation: str
    reason: str
    timestamp: float = Field(default_factory=time.time)


class StatusUpdate(BaseModel):
    status: PipelineStatus
    message: str = ""
    audio_quality: AudioQuality | None = None
    timestamp: float = Field(default_factory=time.time)


class ContextReady(BaseModel):
    topic: str
    keywords: list[str]
    style: str
    source: str


class ErrorMessage(BaseModel):
    code: str
    message: str
    recoverable: bool = True


class ServerMessage(BaseModel):
    type: OutputType
    payload: dict
    timestamp: float = Field(default_factory=time.time)
