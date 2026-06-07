"""谛听辨伪 — 回溯修正：新上下文→检查前文翻译→自动纠错"""
import logging
from collections import deque

from config import config

logger = logging.getLogger("diting.corrector")

_CHECK_PROMPT = (
    "你是翻译校对员。根据最新翻译，检查前面的翻译记录是否需要修正。\n\n"
    "[翻译记录]\n"
    "{history}\n\n"
    "[最新翻译]\n"
    "原文: {new_source}\n"
    "译文: {new_translation}\n\n"
    "判断: 最新翻译是否说明前文中某个术语或句子的翻译有误？\n"
    "如果不需要修正，回复: NO_FIX\n"
    "如果需要修正，回复: FIX: segment_id=<id> | new=<修正后的译文> | reason=<原因>"
)


class Corrector:
    """回溯修正引擎"""

    def __init__(self):
        self._history: deque[dict] = deque(maxlen=5)
        self._last_check = ""

    def feed(self, seg_id: str, source: str, translation: str):
        self._history.append({
            "id": seg_id, "source": source, "translation": translation,
        })

    def build_check_text(self, new_source: str, new_translation: str) -> str | None:
        """构建校对 prompt，返回 None 表示无需检查"""
        if len(self._history) < 2:
            return None

        recent = list(self._history)[-4:]  # 最近 4 条
        lines = []
        for h in recent:
            lines.append(f"  {h['id']}: {h['source']} → {h['translation']}")

        check_text = _CHECK_PROMPT.format(
            history="\n".join(lines),
            new_source=new_source,
            new_translation=new_translation,
        )
        # 去重：和上次检查内容一样就跳过
        if check_text == self._last_check:
            return None
        self._last_check = check_text
        return check_text

    def parse_response(self, response: str) -> dict | None:
        """解析 LLM 回复，返回 correction 或 None"""
        if not response or "NO_FIX" in response.upper():
            return None

        import re
        m = re.search(r"FIX:\s*segment_id\s*=\s*(\S+)", response)
        if not m:
            return None
        seg_id = m.group(1).strip()

        m2 = re.search(r"new\s*=\s*(.+?)(?:\s*\||\s*$)(?:\s*reason\s*=)?", response)
        new_translation = m2.group(1).strip() if m2 else ""

        m3 = re.search(r"reason\s*=\s*(.+)", response)
        reason = m3.group(1).strip() if m3 else "上下文修正"

        return {
            "segment_id": seg_id,
            "old_translation": "",
            "new_translation": new_translation,
            "reason": reason,
        }
