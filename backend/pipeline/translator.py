"""翻译引擎 — 可替换后端"""
import asyncio
import logging
from abc import ABC, abstractmethod
from config import config

logger = logging.getLogger("diting.translator")


class TranslatorBackend(ABC):
    """翻译后端统一接口"""

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
        if config.anthropic_api_key:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=config.anthropic_api_key)
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
                model=config.translator.model,
                max_tokens=config.translator.max_tokens,
                temperature=config.translator.temperature,
                system=config.translator.system_prompt,
                messages=[{"role": "user", "content": text}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            logger.error(f"Claude 翻译失败: {e}")
            return text


class OpenAITranslator(TranslatorBackend):
    """OpenAI 兼容 API 英→中（支持任意 OpenAI 兼容接口）"""

    def __init__(self):
        import os
        self._client = None
        self._model = config.translator.model
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "")
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
                    {"role": "system", "content": config.translator.system_prompt},
                    {"role": "user", "content": text},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI 翻译失败: {e}")
            return text


def create_translator(provider: str = "") -> TranslatorBackend:
    """工厂：按配置或自动检测可用 API key"""
    import os
    provider = provider or getattr(config, "translator_provider", "auto")
    if provider == "claude":
        return ClaudeTranslator()
    if provider == "openai":
        return OpenAITranslator()
    # auto: 检测哪个 key 可用
    if os.getenv("OPENAI_API_KEY"):
        return OpenAITranslator()
    if config.anthropic_api_key:
        return ClaudeTranslator()
    logger.warning("未配置翻译 API key，将回退原文")
    return ClaudeTranslator()  # 无 key 时 Claude 内部回退
