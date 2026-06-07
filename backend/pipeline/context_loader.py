"""闻境 — 语境预加载：URL抓取 → 关键词提取 → 术语注入翻译"""
import logging
import re
import time
from html.parser import HTMLParser

import httpx

from config import config
from models.schemas import ContextUpdate, ContextReady

logger = logging.getLogger("diting.context")

_cache: dict[str, tuple[ContextReady, float]] = {}


class _TextExtractor(HTMLParser):
    """从 HTML 中提取纯文本 + <title>"""
    def __init__(self):
        super().__init__()
        self.title = ""
        self.text: list[str] = []
        self._in_title = False
        self._skip = {"script", "style", "noscript", "head"}
        self._skip_stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._skip:
            self._skip_stack.append(tag)
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_stack:
            return
        if self._in_title:
            self.title += data.strip()
        else:
            t = data.strip()
            if t:
                self.text.append(t)


def _fetch_url(url: str, timeout: int = 10) -> str | None:
    """抓取 URL 并提取文本"""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                       headers={"User-Agent": "DitingVeritas/1.0"})
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"URL 抓取失败: {url} — {e}")
        return None

    try:
        p = _TextExtractor()
        p.feed(r.text)
        title = p.title or ""
        body = " ".join(p.text)
        # 截取前 3000 字符
        body = body[:3000]
        if title:
            return f"标题: {title}\n\n内容: {body}"
        return body
    except Exception as e:
        logger.warning(f"HTML 解析失败: {e}")
        return None


def _infer_context(text: str) -> ContextReady:
    """从文本中提取关键词和主题（纯规则，不调 LLM）"""
    # 取前 500 字作为上下文摘要
    snippet = text[:500].replace("\n", " ").strip()

    # 简单关键词提取：长度 >= 2 的中文/英文词，按频率取 top 8
    words = re.findall(r"[一-鿿]{2,}|[a-zA-Z]{3,}", snippet)
    freq: dict[str, int] = {}
    for w in words:
        wl = w.lower()
        if wl not in {"the", "and", "for", "that", "this", "with", "from", "are", "was", "were",
                       "have", "has", "had", "not", "but", "all", "can", "will", "would", "been",
                       "our", "their", "your", "its", "his", "her", "they", "them", "also"}:
            freq[wl] = freq.get(wl, 0) + 1
    top = sorted(freq.items(), key=lambda x: -x[1])[:8]
    keywords = [k for k, _ in top]

    topic = snippet[:80] if snippet else "未知主题"
    return ContextReady(topic=topic, keywords=keywords, style="正式", source="url")


def load_context(ctx: ContextUpdate | None) -> ContextReady | None:
    """加载语境：URL抓取 / 关键词直用，带缓存"""
    if ctx is None:
        return None

    cache_key = ctx.url or ",".join(ctx.keywords or []) or ctx.title or ""
    if cache_key and cache_key in _cache:
        cached, ts = _cache[cache_key]
        if time.time() - ts < config.context.cache_ttl_minutes * 60:
            logger.info(f"语境缓存命中: {cached.topic[:40]}")
            return cached
        del _cache[cache_key]

    # 有 URL → 抓取
    if ctx.url:
        text = _fetch_url(ctx.url)
        if text:
            result = _infer_context(text)
            _cache[cache_key] = (result, time.time())
            logger.info(f"语境加载: {result.topic[:40]}, 关键词={result.keywords}")
            return result

    # 只有关键词或标题 → 直接用
    if ctx.keywords or ctx.title:
        result = ContextReady(
            topic=ctx.title or "",
            keywords=ctx.keywords or [],
            style="正式",
            source="manual",
        )
        if cache_key:
            _cache[cache_key] = (result, time.time())
        logger.info(f"语境手动: topic={result.topic[:40]}, keywords={result.keywords}")
        return result

    return None


def build_context_block(ctx: ContextReady | None) -> str:
    """将语境转为 system_prompt 注入块"""
    if ctx is None:
        return ""
    parts: list[str] = []
    if ctx.topic:
        parts.append(f"当前语境/主题：{ctx.topic}")
    if ctx.keywords:
        parts.append(f"关键术语参考：{', '.join(ctx.keywords)}")
    if parts:
        parts.append("请在翻译时保持上述术语和语境一致。")
        return "\n".join(parts)
    return ""
