"""翻译引擎 — 可替换后端"""
import asyncio
import logging
from abc import ABC, abstractmethod
from config import config, LANG_NAMES

logger = logging.getLogger("diting.translator")


class TranslatorBackend(ABC):
    """翻译后端统一接口"""

    context_block: str = ""  # 闻境注入块，由管道设置

    def correction_check(self, prompt: str) -> str:
        """纠错检查：用校对 prompt 直调 LLM，不走翻译 system_prompt"""
        return ""

    def _build_system(self, base: str) -> str:
        if self.context_block:
            return base + "\n\n" + self.context_block
        return base

    @abstractmethod
    def translate(self, text: str) -> str:
        ...

    async def translate_async(self, text: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.translate, text)


class ClaudeTranslator(TranslatorBackend):
    """Claude API 英→中"""

    def __init__(self):
        self._client = None
        self._model = config.translator.model
        if self._model == "auto":
            self._model = "claude-sonnet-4-6"
        if config.translator.anthropic_api_key:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=config.translator.anthropic_api_key)
                logger.info("Claude 翻译就绪")
            except ImportError:
                logger.error("未安装 anthropic SDK")

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""
        if self._client is None:
            return text
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=config.translator.max_tokens,
                temperature=config.translator.temperature,
                system=self._build_system(config.translator.system_prompt.replace("{src_lang}", LANG_NAMES.get(config.asr.language, "英文"))),
                messages=[{"role": "user", "content": text}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            logger.error(f"Claude 翻译失败: {e}")
            return text

    def correction_check(self, prompt: str) -> str:
        if not self._client: return "NO_FIX"
        try:
            resp = self._client.messages.create(
                model=self._model, max_tokens=128, temperature=0.1,
                system="你是翻译校对员。根据最新译文检查前文是否需要修正。不需要回复NO_FIX。需要回复FIX:segment_id=... | new=... | reason=...",
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            logger.debug(f"纠错检查失败: {e}")
            return "NO_FIX"


class OpenAITranslator(TranslatorBackend):
    """OpenAI 兼容 API 英→中（支持任意 OpenAI 兼容接口）"""

    def __init__(self):
        self._client = None
        self._model = config.translator.model
        if self._model == "auto":
            self._model = "gpt-4o-mini"
        api_key = config.translator.openai_api_key
        base_url = config.translator.openai_base_url
        if api_key:
            try:
                from openai import OpenAI
                kwargs = {"api_key": api_key}
                if base_url:
                    kwargs["base_url"] = base_url
                self._client = OpenAI(**kwargs)
                logger.info(f"OpenAI 翻译就绪 ({self._model})")
            except ImportError:
                logger.error("未安装 openai SDK")

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""
        if self._client is None:
            return text
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                max_tokens=config.translator.max_tokens,
                temperature=config.translator.temperature,
                messages=[
                    {"role": "system", "content": self._build_system(config.translator.system_prompt.replace("{src_lang}", LANG_NAMES.get(config.asr.language, "英文")))},
                    {"role": "user", "content": text},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI 翻译失败: {e}")
            return text

    def correction_check(self, prompt: str) -> str:
        if not self._client: return "NO_FIX"
        try:
            resp = self._client.chat.completions.create(
                model=self._model, max_tokens=128, temperature=0.1,
                messages=[
                    {"role": "system", "content": "你是翻译校对员。检查前文是否需要修正。不需要回复NO_FIX。需要回复FIX:segment_id=... | new=... | reason=..."},
                    {"role": "user", "content": prompt},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.debug(f"纠错检查失败: {e}")
            return "NO_FIX"

    async def translate_stream_async(self, text: str):
        """流式翻译，逐 token 产出（异步）"""
        if not text.strip() or self._client is None:
            return
        try:
            from openai import AsyncOpenAI
            aclient = AsyncOpenAI(
                api_key=self._client.api_key,
                base_url=str(self._client.base_url),
            )
            stream = await aclient.chat.completions.create(
                model=self._model, max_tokens=config.translator.max_tokens,
                temperature=config.translator.temperature, stream=True,
                messages=[
                    {"role": "system", "content": self._build_system(config.translator.system_prompt.replace("{src_lang}", LANG_NAMES.get(config.asr.language, "英文")))},
                    {"role": "user", "content": text},
                ],
            )
            async for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield token
        except Exception as e:
            logger.debug(f"流式翻译异常: {e}")


def create_translator(provider: str = "") -> TranslatorBackend:
    """工厂：按配置或自动检测可用 API key"""
    provider = provider or config.translator.provider
    if provider == "claude":
        return ClaudeTranslator()
    if provider == "openai":
        return OpenAITranslator()
    # auto: 检测哪个 key 可用
    if config.translator.openai_api_key:
        return OpenAITranslator()
    if config.translator.anthropic_api_key:
        return ClaudeTranslator()
    logger.warning("未配置翻译 API key，将回退原文")
    return ClaudeTranslator()
