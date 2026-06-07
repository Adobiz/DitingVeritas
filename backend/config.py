"""DitingVeritas 配置"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AudioConfig:
    sample_rate: int | None = None  # None=自动检测设备原生率，非None=强制
    channels: int = 1
    block_size: int = 1024
    device_index: int | None = None
    dtype: str = "float32"


@dataclass
class VADConfig:
    threshold: float = 0.5
    min_speech_duration_ms: int = 400   # 低于此忽略
    min_silence_duration_ms: int = 500  # 句间静音阈值（防碎片化）
    speech_pad_ms: int = 200
    sample_rate: int = 16000


@dataclass
class ASRConfig:
    model_size: str = "small"
    compute_type: str = "int8"
    language: str = "en"
    beam_size: int = 5
    vad_filter: bool = False  # 由外部 VAD 模块处理


@dataclass
class ASRProviderConfig:
    provider: str = field(default_factory=lambda: os.getenv("ASR_PROVIDER", "local"))
    aliyun_app_key: str = field(default_factory=lambda: os.getenv("ALIYUN_APP_KEY", ""))
    aliyun_token: str = field(default_factory=lambda: os.getenv("ALIYUN_TOKEN", ""))


@dataclass
class TranslatorConfig:
    provider: str = field(default_factory=lambda: os.getenv("TRANSLATOR_PROVIDER", "auto"))
    model: str = field(default_factory=lambda: os.getenv("TRANSLATOR_MODEL", "auto"))
    temperature: float = 0.3
    max_tokens: int = 256
    system_prompt: str = field(
        default="你是同声传译专家。将英文翻译成简洁中文。只输出译文。"
    )
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))


@dataclass
class ContextConfig:
    inference_duration_seconds: int = 15
    cache_ttl_minutes: int = 60


@dataclass
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    asr_provider: ASRProviderConfig = field(default_factory=ASRProviderConfig)
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    context: ContextConfig = field(default_factory=ContextConfig)


config = Config()
