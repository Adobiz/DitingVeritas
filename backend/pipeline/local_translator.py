"""本地翻译后端 — CTranslate2 NLLB 模型"""
import logging
import os

from config import config
from pipeline.translator import TranslatorBackend

logger = logging.getLogger("diting.local-tl")

# NLLB-200 语言代码映射
NLLB_SRC = {
    "en": "eng_Latn", "zh": "zho_Hans", "ja": "jpn_Jpan",
    "ko": "kor_Hang", "fr": "fra_Latn", "de": "deu_Latn",
    "es": "spa_Latn", "ru": "rus_Cyrl", "ar": "arb_Arab",
    "pt": "por_Latn", "it": "ita_Latn",
}
NLLB_TGT = "zho_Hans"

_model = None
_tokenizer = None
_loaded_path = ""


def _load_model(model_path: str):
    global _model, _tokenizer, _loaded_path
    if _loaded_path == model_path and _model is not None:
        return

    logger.info(f"加载本地模型: {model_path}")
    import ctranslate2
    _model = ctranslate2.Translator(model_path, device=config.asr.device)

    # 尝试本地 tokenizer，没有就从 HF 下载
    tok_path = os.path.join(model_path, "tokenizer")
    if os.path.isdir(tok_path):
        from transformers import AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(tok_path)
    else:
        from transformers import AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(
            "facebook/nllb-200-distilled-600M", src_lang=NLLB_SRC.get(config.asr.language, "eng_Latn"))

    _loaded_path = model_path
    logger.info("本地翻译模型就绪")


class LocalTranslator(TranslatorBackend):
    def __init__(self, model_path: str = ""):
        self._path = model_path or config.translator.local_path

    def _beam_size(self) -> int:
        # 强化模式用贪婪解码，均衡/稳定用 beam=2
        if getattr(config, "pipeline_mode", "balanced") == "turbo":
            return 1
        return 2

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""
        try:
            _load_model(self._path)
            src_code = NLLB_SRC.get(config.asr.language, "eng_Latn")
            _tokenizer.src_lang = src_code
            tokens = _tokenizer.convert_ids_to_tokens(_tokenizer.encode(text))
            results = _model.translate_batch(
                [tokens],
                beam_size=self._beam_size(),
                max_decoding_length=64,
                target_prefix=[[NLLB_TGT]],
            )
            output = results[0].hypotheses[0]
            text = _tokenizer.decode(_tokenizer.convert_tokens_to_ids(output))
            # 去掉可能残留的目标语言前缀
            if text.startswith("zho_Hans "):
                text = text[9:]
            elif text.startswith("zho_Hans"):
                text = text[8:]
            return text
        except Exception as e:
            logger.error(f"本地翻译失败: {e}")
            return text

    async def translate_stream_async(self, text: str):
        """模拟流式：逐字 yield 完整结果，匹配 API 打字机效果"""
        result = self.translate(text)
        for ch in result:
            yield ch
            await __import__("asyncio").sleep(0.02)
