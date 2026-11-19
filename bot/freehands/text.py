"""Text analysis for auto-moderation and code sensing.

All pure functions: given a string, decide. That keeps the rules unit-testable
and the bot logic free of regex soup.
"""

from __future__ import annotations

import re
import time
from collections import deque

SLUR = re.compile(r"(?i)\bn[i1!|l]+[gq]{2,}\w*")
INVITE = re.compile(r"(?i)\b(?:discord(?:app)?\.(?:gg|com/invite)|dsc\.gg)/[a-z0-9-]+")
EVERYONE = re.compile(r"@(everyone|here)\b")

_CODE_HINT = re.compile(r"\bcode\s*[-:#]?\s*\d", re.I)


def has_slur(text: str) -> bool:
    return bool(text) and bool(SLUR.search(text))


def has_invite(text: str) -> bool:
    return bool(text) and bool(INVITE.search(text))


def mentions_everyone(text: str) -> bool:
    return bool(text) and bool(EVERYONE.search(text))


def mentions_bot(text: str, bot_id: int) -> bool:
    if not text:
        return False
    return f"<@{bot_id}>" in text or f"<@!{bot_id}>" in text


def is_punish_request(text: str) -> bool:
    """`@freehands punish dyllan` and close variants."""
    if not text:
        return False
    lowered = text.lower()
    if not any(word in lowered for word in ("punish", "punis", "sanction")):
        return False
    return any(alias in lowered for alias in ("dyllan", "mysterious", "stranger", " ms "))


def is_caps_flood(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 18:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.85


class SpamTracker:
    """Sliding-window message counter per user."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[int, deque[float]] = {}

    def hit(self, user_id: int, now: float | None = None) -> int:
        now = time.time() if now is None else now
        bucket = self._hits.setdefault(user_id, deque())
        bucket.append(now)
        cutoff = now - self.window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        return len(bucket)

    def clear(self, user_id: int) -> None:
        self._hits.pop(user_id, None)


class RaidTracker:
    """Join-rate detector: too many joins inside a short window."""

    def __init__(self, joins: int, window: float) -> None:
        self.joins = joins
        self.window = window
        self._recent: deque[float] = deque()

    def hit(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self._recent.append(now)
        cutoff = now - self.window
        while self._recent and self._recent[0] < cutoff:
            self._recent.popleft()
        return len(self._recent) >= self.joins


def parse_duration(token: str) -> int | None:
    """`10m`, `2h`, `4d`, `90s`, or a bare number of seconds."""
    if not token:
        return None
    match = re.fullmatch(r"(\d+)\s*([smhdw]?)", token.strip().lower())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2) or "s"
    scale = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    return amount * scale


def human_duration(seconds: int) -> str:
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size and seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def looks_like_code(text: str) -> bool:
    return bool(text) and bool(_CODE_HINT.search(text))
