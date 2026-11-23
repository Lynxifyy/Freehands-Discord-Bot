"""Process wiring: token, gateway, poll fallback, maintenance loop."""

from __future__ import annotations

import time
from pathlib import Path

from .codebook import Codebook
from .config import GUILD_ID, MAIN_CHAT_ID, env_flag
from .console import BotApi
from .engine import Engine
from . import keeper
from .gateway import Gateway
from .log import log, stats
from .rest import Rest, RestError
from .store import Store
from .vault import load_token

MAINTENANCE_INTERVAL = 15.0
POLL_INTERVAL = 2.0


def build(root: Path | None = None) -> tuple[Rest, Store, Engine]:
    root = root or Path(__file__).resolve().parent.parent
    token = load_token()
    rest = Rest(token)
    store = Store(root / "state.json")
    store.load()
    book = Codebook.load(root / "codes.json")
    engine = Engine(rest, store, book)
    return rest, store, engine


def prime(engine: Engine) -> None:
    """Load the bot's own roles so hierarchy checks are meaningful."""
    try:
        me = engine.rest.me()
        member = engine.rest.member(GUILD_ID, int(me["id"]))
        engine.mod.refresh_roles({int(r) for r in (member or {}).get("roles", [])})
    except RestError as exc:
        log.warning("role bootstrap failed: %s", exc)
    engine.mod.seed_known_bans()
    # The ops channel is created on demand, the first time an operator code or
    # `+ops` needs it. Making it at boot left an empty channel in the server
    # from the moment the bot started, which is a visible hint that nothing
    # was happening.
    engine.tempown.start_sweeper()
    if engine.tempown.sweep():
        log.info("an expired temporary-ownership grant was reclaimed at startup")


def maintenance(engine: Engine) -> None:
    s = engine.settings
    if s.anti_ban:
        engine.mod.anti_ban_sweep()
    if s.keep_banned:
        engine.mod.enforce_keep_banned()
    for target, moderator in engine.mod.new_bans_from_audit():
        if target in s.keep_banned or not s.anti_ban:
            continue
        if engine.rest.unban(GUILD_ID, target, "anti-ban (audit)") in (200, 204):
            stats.bump("unbans")
            log.warning("anti-ban reversed audit ban on %s (by %s)", target, moderator)
            engine.send(
                MAIN_CHAT_ID,
                f"<@{target}> was banned by <@{moderator}>. Anti-ban reversed it.",
            )
    engine.store.known_bans = set(engine.mod.ban_list())
    engine.store.save()


def poll_once(engine: Engine, seen: set[int]) -> int:
    fresh = 0
    for row in sorted(engine.rest.messages(MAIN_CHAT_ID, limit=20), key=lambda m: int(m["id"])):
        message_id = int(row["id"])
        if message_id in seen:
            continue
        seen.add(message_id)
        fresh += 1
        engine.on_message(row)
    return fresh


def run() -> None:
    rest, store, engine = build()
    log.info(
        "Freehands %s starting | anti-ban=%s moderation=%s code-sense=%s gateway=%s",
        "2.0", store.settings.anti_ban, store.settings.moderation_enabled,
        store.settings.codes_enabled, env_flag("FH_GATEWAY", True),
    )
    prime(engine)

    # The console API runs inside this process so settings changes land on the
    # live objects instead of being overwritten by the next state save.
    api = BotApi(engine)
    api.start()

    # The supervisor keeps this process alive; this keeps the supervisor alive.
    # Without it, a dead supervisor meant a dead public port that no app could
    # wake, because a request cannot reach a process that is not listening.
    if env_flag("FH_KEEPER", True):
        keeper.start()

    seen = {int(m["id"]) for m in rest.messages(MAIN_CHAT_ID, limit=25)}
    gateway = None
    if env_flag("FH_GATEWAY", True):
        gateway = Gateway(
            rest.token,
            lambda name, data: engine.handle_event(name, data),
            on_ready=lambda _: log.info("ready"),
        )
        gateway.start()
        if gateway.wait_ready(20):
            log.info("gateway live — commands are event-driven")
        else:
            log.warning("gateway not ready; falling back to polling")

    last_maintenance = 0.0
    while True:
        try:
            if not (gateway and gateway.is_alive()):
                if poll_once(engine, seen):
                    log.info("poll picked up new messages")
            now = time.time()
            if now - last_maintenance >= MAINTENANCE_INTERVAL:
                last_maintenance = now
                maintenance(engine)
            store.save()
        except RestError as exc:
            log.error("loop error: %s", exc)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # keep the bot alive through anything unexpected
            log.exception("unexpected loop error: %r", exc)
        time.sleep(POLL_INTERVAL if not (gateway and gateway.is_alive()) else 1.0)
