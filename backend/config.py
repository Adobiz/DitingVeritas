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
    min_speech_duration_ms: int = 500   # 低于此忽略
    min_silence_duration_ms: int = 800  # 句间静音阈值（防碎片化）
    speech_pad_ms: int = 200
    sample_rate: int = 16000


@dataclass
class ASRConfig:
    model_size: str = "tiny"
    compute_type: str = "int8"
    device: str = "cpu"
    language: str = "en"
    beam_size: int = 5
    vad_filter: bool = False  # 由外部 VAD 模块处理


@dataclass
class ASRProviderConfig:
    provider: str = field(default_factory=lambda: os.getenv("ASR_PROVIDER", "local"))
    aliyun_app_key: str = field(default_factory=lambda: os.getenv("ALIYUN_APP_KEY", ""))
    aliyun_access_key: str = field(default_factory=lambda: os.getenv("ALIYUN_ACCESS_KEY", ""))
    aliyun_access_secret: str = field(default_factory=lambda: os.getenv("ALIYUN_ACCESS_SECRET", ""))


@dataclass
class TranslatorConfig:
    provider: str = field(default_factory=lambda: os.getenv("TRANSLATOR_PROVIDER", "auto"))
    model: str = field(default_factory=lambda: os.getenv("TRANSLATOR_MODEL", "auto"))
    temperature: float = 0.3
    max_tokens: int = 256
    system_prompt: str = field(
        default=(
            "你是实时同声传译 AI。将{src_lang}实时翻译为中文。\n"
            "规则：\n"
            "1. 输入可能是不完整片段，请根据语义合理推测并补齐，而非字面直译\n"
            "2. 只输出中文，每段≤25字，口语化、流畅自然\n"
            "3. 保持术语和风格一致（如前文提到人名/品牌名，沿用不重译）\n"
            "4. 若输入仅为单词/短语，结合语境补全为通顺短句"
        )
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


    pipeline_mode: str = field(default_factory=lambda: os.getenv("PIPELINE_MODE", "balanced"))

LANG_NAMES = {"en":"英文","zh":"中文","ja":"日语","ko":"韩语","fr":"法语","de":"德语","es":"西班牙语","ru":"俄语","ar":"阿拉伯语","pt":"葡萄牙语","it":"意大利语"}

config = Config()
