"""JSON persistence for settings, strikes, snapshots and incidents.

A single small file is enough here; SQLite was more machinery than the data
justifies and it made the state hard to inspect during an incident.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import Settings
from .log import log


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.settings = Settings()
        self.strikes: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, list[int]] = {}
        self.known_bans: set[int] = set()
        self.seen: set[int] = set()
        self.incidents: list[dict[str, Any]] = []
        self.questions: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._last_save = 0.0

    # -- io ---------------------------------------------------------------
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.settings = Settings.from_json(raw.get("settings", {}))
        self.strikes = {k: v for k, v in raw.get("strikes", {}).items()}
        self.snapshots = {k: list(v) for k, v in raw.get("snapshots", {}).items()}
        self.known_bans = {int(x) for x in raw.get("known_bans", [])}
        self.incidents = raw.get("incidents", [])[-200:]
        self.questions = raw.get("questions", {})

    def save(self, force: bool = False) -> None:
        now = time.time()
        if not force and not self._dirty and now - self._last_save < 5:
            return
        payload = {
            "settings": self.settings.to_json(),
            "strikes": self.strikes,
            "snapshots": self.snapshots,
            "known_bans": sorted(self.known_bans),
            "incidents": self.incidents[-200:],
            "questions": self.questions,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"))
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("state save failed: %s", exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return
        self._dirty = False
        self._last_save = now

    def touch(self) -> None:
        self._dirty = True

    # -- strikes ----------------------------------------------------------
    def strike(self, user_id: int, kind: str) -> int:
        row = self.strikes.setdefault(str(user_id), {})
        row[kind] = int(row.get(kind, 0)) + 1
        self.touch()
        return row[kind]

    def get_strikes(self, user_id: int, kind: str | None = None) -> int | dict:
        row = self.strikes.get(str(user_id), {})
        return row if kind is None else int(row.get(kind, 0))

    def clear_strikes(self, user_id: int) -> None:
        self.strikes.pop(str(user_id), None)
        self.touch()

    # -- incidents --------------------------------------------------------
    def add_incident(self, record: dict[str, Any]) -> None:
        self.incidents.append(record)
        self.incidents = self.incidents[-200:]
        self.touch()
