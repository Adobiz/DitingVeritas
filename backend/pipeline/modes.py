"""管道运行模式 — 强化 / 均衡 / 稳定"""
from dataclasses import dataclass


@dataclass
class PipelineMode:
    label: str
    asr_interval: float           # ASR 触发频率（秒）
    asr_buffer_sec: float         # 音频缓冲上限（秒）
    vad_silence_ms: int           # VAD 静音判定（毫秒）
    translate_debounce_ms: int    # 翻译防抖（毫秒）
    min_words: int
    context_len: int
    show_interim: bool
    drop_stale: bool
    fallback_original: bool


MODES = {
    "turbo": PipelineMode(
        label="强化",
        asr_interval=1.5,
        asr_buffer_sec=1.5,
        vad_silence_ms=300,
        translate_debounce_ms=0,
        min_words=1,
        context_len=1,
        show_interim=True,
        drop_stale=True,
        fallback_original=False,
    ),
    "balanced": PipelineMode(
        label="均衡",
        asr_interval=0.35,
        asr_buffer_sec=4,
        vad_silence_ms=600,
        translate_debounce_ms=150,
        min_words=2,
        context_len=3,
        show_interim=True,
        drop_stale=True,
        fallback_original=True,
    ),
    "stable": PipelineMode(
        label="稳定",
        asr_interval=0.5,          # 后台频繁推理，翻译预热
        asr_buffer_sec=8,          # 够完整句子，推理更快
        vad_silence_ms=700,        # 比均衡保守，比原来快
        translate_debounce_ms=200, # 句子完整，debounce 可短
        min_words=3,               # 短句及时翻
        context_len=5,             # 保留 5 句上下文
        show_interim=False,        # 前端不闪，后台仍预热
        drop_stale=False,
        fallback_original=True,
    ),
}

DEFAULT_MODE = MODES["balanced"]


def get_mode(name: str) -> PipelineMode:
    return MODES.get(name, DEFAULT_MODE)
