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
        asr_interval=0.2,
        asr_buffer_sec=2,
        vad_silence_ms=300,
        translate_debounce_ms=100,
        min_words=1,
        context_len=1,
        show_interim=True,
        drop_stale=True,
        fallback_original=False,
    ),
    "balanced": PipelineMode(
        label="均衡",
        asr_interval=0.5,
        asr_buffer_sec=6,
        vad_silence_ms=800,
        translate_debounce_ms=300,
        min_words=3,
        context_len=3,
        show_interim=True,
        drop_stale=True,
        fallback_original=True,
    ),
    "stable": PipelineMode(
        label="稳定",
        asr_interval=0.8,
        asr_buffer_sec=10,
        vad_silence_ms=1000,
        translate_debounce_ms=400,
        min_words=5,
        context_len=5,
        show_interim=False,
        drop_stale=False,
        fallback_original=True,
    ),
}

DEFAULT_MODE = MODES["balanced"]


def get_mode(name: str) -> PipelineMode:
    return MODES.get(name, DEFAULT_MODE)
