"""管道运行模式 — 强化 / 均衡 / 稳定"""
from dataclasses import dataclass


@dataclass
class PipelineMode:
    label: str                    # 显示名
    asr_interval: float           # ASR 推理频率（秒）
    asr_buffer_sec: float         # 音频缓冲上限（秒）
    vad_silence_ms: int           # VAD 静音判定（毫秒）
    translate_debounce_ms: int    # 翻译防抖（毫秒）
    min_words: int                # 短句阈值（词数）
    context_len: int              # 上下文句子数
    show_interim: bool            # 是否显示 interim
    drop_stale: bool              # 是否丢弃过期 partial
    fallback_original: bool       # 未翻译时是否显示原文


MODES = {
    "turbo": PipelineMode(
        label="强化",
        asr_interval=0.3,
        asr_buffer_sec=4,
        vad_silence_ms=500,
        translate_debounce_ms=150,
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
        asr_interval=1.0,
        asr_buffer_sec=10,
        vad_silence_ms=1200,
        translate_debounce_ms=600,
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
