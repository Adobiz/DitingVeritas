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
            return text  # 无 key 回退原文
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
            logger.error(f"翻译失败: {e}")
            return text


def create_translator(provider: str = "") -> TranslatorBackend:
    """工厂：根据配置或环境变量创建翻译实例"""
    provider = provider or getattr(config, "translator_provider", "claude")
    if provider == "claude":
        return ClaudeTranslator()
    raise ValueError(f"未知翻译后端: {provider}")
