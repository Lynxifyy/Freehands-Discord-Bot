"""Rolling event log for the operator console.

The gateway delivers message, delete, edit and presence events. This module
turns them into one flat record shape and keeps the recent ones in memory, so
the Android app can show a live feed without the bot keeping a database.

Records are also appended to a JSONL file so a console opened after a restart
still has context. The file is capped: a long-running bot must not fill the
disk with chat history.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

MAX_RECORDS = 2000
MAX_FILE_BYTES = 8 * 1024 * 1024


# Discord sends stickers as `sticker_items`; format_type says how to fetch it.
# 1=PNG, 2=APNG, 3=Lottie (JSON, not an image), 4=GIF.
_STICKER_EXT = {1: "png", 2: "apng", 3: "json", 4: "gif"}

# <:name:id> for static, <a:name:id> for animated custom emoji.
_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_~]+):(\d{5,})>")


def _emoji(text: str) -> list[dict[str, str]]:
    """Pull custom emoji out of message text so they render as pictures.

    Unicode emoji need nothing: the console font already draws them. Custom
    emoji are images referenced by id, and the raw `<:name:id>` markup is
    unreadable, so they become media entries instead.
    """
    out: list[dict[str, str]] = []
    for animated, name, eid in _EMOJI_RE.findall(text or ""):
        out.append({
            "kind": "emoji",
            "url": f"https://cdn.discordapp.com/emojis/{eid}.{'gif' if animated else 'png'}",
            "name": f":{name}:",
            "size": "",
        })
    return out


def _media(msg: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten every kind of attachment into one list of links.

    Discord splits media across several fields: `attachments` for uploads,
    `sticker_items` for stickers and `embeds` for link previews and GIFs. The
    console wants one list, so each entry carries its own kind and URL.
    """
    out: list[dict[str, str]] = []
    for a in msg.get("attachments") or []:
        kind = "image"
        ctype = (a.get("content_type") or "").lower()
        if ctype.startswith("video"):
            kind = "video"
        elif ctype.startswith("audio"):
            kind = "audio"
        elif ctype and not ctype.startswith("image"):
            kind = "file"
        out.append({
            "kind": kind,
            "url": a.get("url") or a.get("proxy_url") or "",
            "name": a.get("filename") or "",
            "size": str(a.get("size") or ""),
        })
    # `sticker_items` is what the API actually sends; `stickers` is the older
    # shape and is only read as a fallback.
    for s in (msg.get("sticker_items") or msg.get("stickers") or []):
        ext = _STICKER_EXT.get(s.get("format_type") or 1, "png")
        out.append({
            "kind": "sticker",
            "url": f"https://cdn.discordapp.com/stickers/{s.get('id')}.{ext}",
            "name": s.get("name") or "",
            "size": "",
        })
    for e in msg.get("embeds") or []:
        etype = (e.get("type") or "").lower()
        url = e.get("url") or ""
        thumb = ((e.get("thumbnail") or {}).get("url")) or ""
        video = ((e.get("video") or {}).get("url")) or ""
        image = ((e.get("image") or {}).get("url")) or ""
        kind = "gif" if etype == "gifv" else "embed"
        # A gifv's `video` is an mp4, which an image loader cannot draw. The
        # thumbnail is the animated still, so prefer it for display and only
        # fall back to the video when there is nothing else.
        link = image or thumb or video or url
        if link:
            out.append({"kind": kind, "url": link, "name": e.get("title") or "", "size": ""})
    return out


def _author(msg: dict[str, Any]) -> dict[str, str]:
    a = msg.get("author") or {}
    member = msg.get("member") or {}
    name = member.get("nick") or a.get("global_name") or a.get("username") or ""
    return {"id": str(a.get("id") or ""), "name": name}


class EventLog:
    """A bounded, thread-safe ring of recent events plus a JSONL mirror."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._rows: deque[dict[str, Any]] = deque(maxlen=MAX_RECORDS)
        self._seq = 0
        if path is not None:
            self._reload()

    def _reload(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines[-MAX_RECORDS:]:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            # Rows written by an older build may predate a field, so the shape
            # is applied here as well as on append.
            self._rows.append({**self._blank(), **row})
            self._seq = max(self._seq, int(row.get("seq") or 0))

    @staticmethod
    def _blank() -> dict[str, Any]:
        """Every record carries the same keys so a client can read one shape
        instead of checking which event type it is looking at.

        Built fresh each time: a shared literal would let two records alias the
        same list, so a later mutation would edit history.
        """
        return {
            "type": "",
            "channel": "",
            "author": {"id": "", "name": ""},
            # Who performed the action, when that differs from the author:
            # the deleter on a delete, the moderator on a purge.
            "actor": {"id": "", "name": ""},
            "text": "",
            "before": "",
            "media": [],
            "platforms": [],
            "message_id": "",
            "reply_to": "",
        }

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        row = {**self._blank(), **row}
        with self._lock:
            self._seq += 1
            row["seq"] = self._seq
            row["at"] = int(time.time())
            self._rows.append(row)
            if self.path is not None:
                self._write(row)
        return row

    def _write(self, row: dict[str, Any]) -> None:
        try:
            if self.path.exists() and self.path.stat().st_size > MAX_FILE_BYTES:
                keep = list(self._rows)[-MAX_RECORDS // 2:]
                self.path.write_text(
                    "".join(json.dumps(r) + "\n" for r in keep), encoding="utf-8"
                )
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        except OSError:
            pass

    # -- record kinds -----------------------------------------------------
    def message(self, msg: dict[str, Any], content: str = "") -> dict[str, Any]:
        # The gateway may blank `content` without the message-content intent, so
        # the caller passes a hydrated copy; fall back to the raw field.
        text = content or (msg.get("content") or "")
        return self._append({
            "type": "message",
            "channel": str(msg.get("channel_id") or ""),
            "author": _author(msg),
            "text": text,
            "media": _media(msg) + _emoji(text),
            "reply_to": str((msg.get("referenced_message") or {}).get("id") or ""),
            "message_id": str(msg.get("id") or ""),
        })

    def deleted(self, data: dict[str, Any], cached: dict[str, Any] | None = None,
                actor: dict[str, str] | None = None) -> dict[str, Any]:
        """A delete event carries only ids, so everything else is recovered.

        Two different people matter here and they are easy to confuse:

        * `author` is whoever wrote the message, taken from our own cache.
        * `actor` is whoever pressed delete - the person, or the bot when
          automod removed it. The gateway event does not say, so the caller
          resolves it from the audit log and passes it in.

        Leaving both empty is what made the console print "unknown deleted a
        message": it was showing the *author* slot, which a delete event never
        fills.
        """
        author = (cached or {}).get("author") or {}
        who = actor or {}
        return self._append({
            "type": "delete",
            "channel": str(data.get("channel_id") or ""),
            "author": {"id": str(author.get("id") or ""), "name": author.get("name") or ""},
            "actor": {"id": str(who.get("id") or ""), "name": str(who.get("name") or "")},
            "text": (cached or {}).get("text") or "",
            "media": (cached or {}).get("media") or [],
            "message_id": str(data.get("id") or ""),
        })

    def edited(self, data: dict[str, Any], old: str = "") -> dict[str, Any]:
        text = data.get("content") or ""
        return self._append({
            "type": "edit",
            "channel": str(data.get("channel_id") or ""),
            "author": _author(data),
            "text": text,
            "before": old,
            "media": _media(data) + _emoji(text),
        })

    def presence(self, data: dict[str, Any]) -> dict[str, Any]:
        """Platform is presence, not a per-message fact.

        Discord reports where a user is currently connected, never which device
        sent a given message. The console labels this column "online from" so it
        is not mistaken for message metadata.
        """
        user = data.get("user") or {}
        status = data.get("status") or "offline"
        clients = data.get("client_status") or {}
        where = [k for k, v in clients.items() if v and v != "offline"]
        return self._append({
            "type": "presence",
            "author": {"id": str(user.get("id") or ""), "name": user.get("username") or ""},
            "text": status,
            "media": [],
            "platforms": sorted(where),
        })

    # -- reads ------------------------------------------------------------
    def recent(self, limit: int = 100, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            rows = [r for r in self._rows if int(r.get("seq") or 0) > after]
        return rows[-limit:]

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = list(self._rows)
        out: dict[str, int] = {}
        for r in rows:
            out[r.get("type", "?")] = out.get(r.get("type", "?"), 0) + 1
        return out

    def author_of(self, message_id: str) -> dict[str, str] | None:
        """The author recorded for a message, or None when we never saw it."""
        row = self.find_message(message_id)
        return (row or {}).get("author") or None

    def find_message(self, message_id: str) -> dict[str, Any] | None:
        """Look up a cached message so a later delete can show what was said."""
        target = str(message_id)
        with self._lock:
            for r in reversed(self._rows):
                if r.get("type") == "message" and str(r.get("message_id") or "") == target:
                    return r
        return None
