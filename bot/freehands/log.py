"""Structured logging plus a tiny in-process metrics counter."""

from __future__ import annotations

import logging
import os
import sys
import time
from collections import Counter

_LEVEL = os.environ.get("FH_LOG", "INFO").upper()


def setup(name: str = "freehands") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, _LEVEL, logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = setup()


class Stats:
    """Cheap counters for the `+stats` command."""

    def __init__(self) -> None:
        self.started = time.time()
        self.counts: Counter[str] = Counter()

    def bump(self, key: str, amount: int = 1) -> None:
        self.counts[key] += amount

    def uptime(self) -> str:
        seconds = int(time.time() - self.started)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if days or hours:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)


stats = Stats()
