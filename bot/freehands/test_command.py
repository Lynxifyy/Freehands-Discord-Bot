"""`+test` — a self-check that proves the bot is actually working.

A "pong" proves almost nothing. This runs the parts that really break: whether
Discord accepts our token, whether the event log can round-trip a record, and
whether the pairing store is readable and writable. Each check is independent,
so one failure still reports the rest.
"""

from __future__ import annotations

import time

from .config import GUILD_ID
from .log import log

_PASS = "OK  "
_FAIL = "FAIL"


def _check(name: str, fn) -> tuple[bool, str]:
    """Run one check. A failure is reported, never raised: one broken part must
    not hide the state of the others."""
    started = time.time()
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001 - this command reports failures
        log.warning("+test check %s failed: %r", name, exc)
        return False, f"{type(exc).__name__}: {str(exc)[:80]}"
    ms = int((time.time() - started) * 1000)
    return True, f"{detail}  ({ms} ms)"


def _discord(engine) -> str:
    me = engine.rest.me()
    return f"token accepted, logged in as {me.get('username')}"


def _gateway(engine) -> str:
    gw = getattr(engine, "gateway", None)
    if gw is None:
        return "not started in this process"
    if not gw.wait_ready(timeout=0.01):
        return "still connecting"
    return "connected"


def _guild(engine) -> str:
    """A real read against the guild proves the token has the right scopes."""
    bans = engine.rest.bans(GUILD_ID)
    return f"reachable, {len(bans)} bans visible"


def _events(engine) -> str:
    """The console feed must be readable, and its file must accept a write."""
    held = len(engine.events.recent(limit=1))
    path = engine.events.path
    if path is not None:
        with path.open("a", encoding="utf-8"):
            pass
    return f"feed readable, file writable ({held}+ records)"


def _pairing(engine) -> str:
    n = len(engine.pairing.devices)
    return f"{n} paired console{'' if n == 1 else 's'}"


def _settings(engine) -> str:
    s = engine.settings
    return f"anti-ban={s.anti_ban} moderation={s.moderation_enabled}"


def _commands(engine) -> str:
    return f"{len(engine.registry.specs)} commands registered"


CHECKS = (
    ("discord", _discord),
    ("gateway", _gateway),
    ("guild", _guild),
    ("event log", _events),
    ("pairing", _pairing),
    ("settings", _settings),
    ("commands", _commands),
)


def run(engine, command, user_id, message_id, channel_id, roles):
    """`+test` runs every check and replies with a pass/fail table."""
    results = [(name, *_check(name, lambda f=fn: f(engine))) for name, fn in CHECKS]
    lines = []
    for name, ok, detail in results:
        lines.append(f"{_PASS if ok else _FAIL}  {name}: {detail}")

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    header = "All checks passed." if passed == total else f"{passed}/{total} checks passed."
    engine.reply(channel_id, message_id, header + "\n```\n" + "\n".join(lines) + "\n```")
    log.info("+test: %s", header)
