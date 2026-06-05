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
    keywords: list[str] | None = None

    @classmethod
    def from_string(cls, s: str):
        """从逗号分隔字符串创建"""
        return cls(keywords=[k.strip() for k in s.split(",") if k.strip()])


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
    timestamp: float = Field(default_factory=time.time)


class ErrorMessage(BaseModel):
    code: str
    message: str
    recoverable: bool = True


Payload = TranslationResult | CorrectionResult | StatusUpdate | ContextReady | ErrorMessage


class ServerMessage(BaseModel):
    type: OutputType
    payload: Payload
    timestamp: float = Field(default_factory=time.time)
