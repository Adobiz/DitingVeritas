"""增量处理器 — 从 faster-whisper 整句输出中提取增量"""
import logging

logger = logging.getLogger("diting.incr")


class IncrementalProcessor:
    def __init__(self):
        self.last_text = ""
        self.confirmed_prefix = ""
        self.confirmed_len = 0

    def process(self, new_text: str) -> dict | None:
        if not new_text or new_text == self.last_text:
            return None
        old = self.last_text
        self.last_text = new_text

        # 纯追加
        if old and new_text.startswith(old):
            delta = new_text[len(old):].strip()
            if not delta:
                return None
            self.confirmed_len = len(old.split())
            return {"type": "append", "delta": delta, "full": new_text,
                    "confirmed_len": self.confirmed_len}

        # 找最长公共前缀
        ow, nw = old.split(), new_text.split()
        lcp = 0
        for x, y in zip(ow, nw):
            if x.lower() == y.lower():
                lcp += 1
            else:
                break

        if lcp == len(ow) == len(nw):
            return None
        stable = " ".join(nw[:lcp]) if lcp > 0 else ""
        changed = " ".join(nw[lcp:])
        if lcp > self.confirmed_len:
            self.confirmed_len = lcp
        return {"type": "correct", "stable": stable, "delta": changed,
                "full": new_text, "confirmed_len": lcp}

    def finalize(self, final_text: str):
        self.last_text = ""
        self.confirmed_len = 0
