"""Event routing, auto-moderation and command dispatch.

`Engine.handle_event` is the single entry point for both the gateway and the
poll fallback, so behaviour cannot diverge between transports.
"""

from __future__ import annotations

import os
import time
from typing import Any

from . import text
from .codebook import Codebook, render_alert
from .commands import Command, Registry, parse, user_id_from
from .config import (
    ARCEUS_ID,
    BOT_ID,
    GUILD_ID,
    LYNX_ID,
    MAIN_CHAT_ID,
    MOD_ROLES,
    OPERATOR_ROLES,
    OWNER_ID,
    PREFIX,
    SLUR_EXEMPT,
    TRACKED_CHANNELS,
    WATCH_ID,
)
from .log import log, stats
from .moderation import Moderator
from .rest import Rest, RestError
from .store import Store

TIER_ORDER = {"owner": 0, "admin": 1, "mod": 2, "user": 3}


def _tracked_channels() -> set[int]:
    raw = os.environ.get("FH_CHANNELS", "").strip()
    if not raw:
        return set(TRACKED_CHANNELS)
    parsed = {int(part) for part in raw.replace(" ", "").split(",") if part.isdigit()}
    return parsed or set(TRACKED_CHANNELS)


class Engine:
    def __init__(self, rest: Rest, store: Store, book: Codebook) -> None:
        self.rest = rest
        self.store = store
        self.book = book
        self.settings = store.settings
        self.mod = Moderator(rest, store, self.settings)
        self.registry = Registry()
        self.spam = text.SpamTracker(self.settings.spam_limit, self.settings.spam_window)
        self.raid = text.RaidTracker(self.settings.raid_joins, self.settings.raid_window)
        self._cooldowns: dict[tuple[int, str], float] = {}
        self._member_roles: dict[int, set[int]] = {}
        self.channels = _tracked_channels()
        from . import cmd_impl  # local import keeps the registry wiring in one place

        cmd_impl.register(self)

    # -- identity ---------------------------------------------------------
    def tier_of(self, user_id: int, roles: set[int]) -> str:
        if user_id in (OWNER_ID, LYNX_ID, ARCEUS_ID):
            return "owner"
        if roles & set(OPERATOR_ROLES):
            return "owner"
        if roles & set(MOD_ROLES):
            return "mod"
        return "user"

    def is_operator(self, user_id: int, roles: set[int]) -> bool:
        return self.tier_of(user_id, roles) in ("owner", "admin", "mod")

    # -- event entry ------------------------------------------------------
    def handle_event(self, name: str, data: dict[str, Any]) -> None:
        handler = {
            "MESSAGE_CREATE": self.on_message,
            "MEMBER_ADD": self.on_member_add,
            "MEMBER_REMOVE": self.on_member_remove,
            "GUILD_BAN_ADD": self.on_ban_add,
        }.get(name)
        if handler:
            handler(data)

    def on_message(self, msg: dict[str, Any]) -> None:
        author = msg.get("author") or {}
        if author.get("bot") or int(author.get("id", 0)) == BOT_ID:
            return
        user_id = int(author["id"])
        content = msg.get("content") or ""
        message_id = int(msg["id"])
        channel_id = int(msg["channel_id"])
        if channel_id not in self.channels:
            return

        # Without the MESSAGE_CONTENT intent the gateway delivers the event but
        # blanks `content`. One REST read recovers it, and the REST endpoint is
        # not intent-gated.
        if not content and not msg.get("_hydrated"):
            content = self._hydrate_content(channel_id, message_id) or ""

        roles = self.roles_for(user_id, msg.get("member"))
        self._member_roles[user_id] = roles
        stats.bump("messages")

        if self.settings.codes_enabled and self.handle_code(
            content, user_id, message_id, channel_id, author
        ):
            return
        if self.settings.moderation_enabled and self.automod(
            user_id, content, message_id, channel_id, roles
        ):
            return
        if content.startswith(PREFIX):
            command = parse(content)
            if command:
                self.dispatch(command, user_id, message_id, channel_id, roles)

    # -- codes ------------------------------------------------------------
    def handle_code(self, content: str, user_id: int, message_id: int,
                    channel_id: int, author: dict) -> bool:
        hit = self.book.sense(content)
        if hit is None:
            return False
        code = hit.code
        extra = [f"<@&{role_id}>" for role_id in code.ping_roles]
        body = render_alert(hit, user_id, author.get("username", ""), OWNER_ID, ARCEUS_ID, extra)

        if code.silence:
            self.rest.delete(channel_id, message_id)
        users = [str(user_id)]
        if code.ping_owner:
            users.append(str(OWNER_ID))
        if code.ping_arceus:
            users.append(str(ARCEUS_ID))
        try:
            self.rest.send(
                MAIN_CHAT_ID,
                body,
                allowed_mentions={
                    "parse": [],
                    "users": list(dict.fromkeys(users)),
                    "roles": [str(r) for r in code.ping_roles],
                },
            )
        except RestError as exc:
            log.error("code alert failed: %s", exc)
        if not code.silence:
            self.rest.react(channel_id, message_id, code.emoji)

        self.store.add_incident({
            "at": int(time.time()),
            "code": code.number,
            "title": code.title,
            "by": user_id,
            "trigger": hit.matched_text,
        })
        stats.bump("codes")
        log.info("code %s (%s) raised by %s", code.number, code.title, user_id)

        if code.number == 12:
            self.mod.set_channel_locked(channel_id, True)
        return True

    # -- auto-moderation --------------------------------------------------
    def automod(self, user_id: int, content: str, message_id: int,
                channel_id: int, roles: set[int]) -> bool:
        if text.has_slur(content) and user_id not in SLUR_EXEMPT:
            self.slur_strike(user_id, message_id, channel_id)
            return True
        if text.mentions_bot(content, BOT_ID) and text.is_punish_request(content):
            self.punish(user_id, message_id, channel_id, roles)
            return True
        if text.has_invite(content) and not self.is_operator(user_id, roles):
            self.rest.delete(channel_id, message_id)
            self.rest.reply(channel_id, message_id, f"<@{user_id}> invites are not allowed here.")
            stats.bump("invites_blocked")
            return True
        count = self.spam.hit(user_id)
        if count >= self.settings.spam_limit and not self.is_operator(user_id, roles):
            self.spam.clear(user_id)
            self.rest.timeout(GUILD_ID, user_id, 600, "spam")
            self.rest.reply(
                channel_id, message_id,
                f"<@{user_id}> slowed down for 10m — {count} messages in "
                f"{int(self.settings.spam_window)}s.",
            )
            stats.bump("spam_timeouts")
            return True
        return False

    def slur_strike(self, user_id: int, message_id: int, channel_id: int) -> None:
        count = self.store.strike(user_id, "slur")
        self.rest.react(channel_id, message_id, "\N{LARGE RED SQUARE}")
        if count == 1:
            self.rest.reply(
                channel_id, message_id,
                f"<@{user_id}> that word is not allowed. Strike 1 of 3.",
            )
        elif count == 2:
            self.rest.timeout(GUILD_ID, user_id, 3600, "slur strike 2")
            self.rest.reply(
                channel_id, message_id,
                f"<@{user_id}> muted for 1h. Strike 2 of 3 — the next one asks "
                f"<@{LYNX_ID}> and <@{ARCEUS_ID}> for a ban.",
            )
        else:
            self.rest.reply(
                channel_id, message_id,
                f"<@{LYNX_ID}> <@{ARCEUS_ID}> <@{user_id}> used it again "
                f"(strike {count}). Ban? `+approve` or `+deny`.",
            )
            self.store.questions["slur"] = {
                "user": user_id, "channel": channel_id, "at": int(time.time()),
            }
        stats.bump("slur_strikes")

    def punish(self, user_id: int, message_id: int, channel_id: int, roles: set[int]) -> None:
        if not self.is_operator(user_id, roles):
            return
        count = self.store.strike(WATCH_ID, "punish")
        self.rest.timeout(GUILD_ID, WATCH_ID, 3600, "punish request")
        self.rest.reply(
            channel_id, message_id, f"Punishment {count} applied to <@{WATCH_ID}> (1h)."
        )
        if count >= self.settings.punish_strikes_to_lock:
            self.rest.send(
                channel_id,
                f"<@{OWNER_ID}> <@{ARCEUS_ID}> <@{LYNX_ID}> — <@{WATCH_ID}> has hit "
                f"{count} punishments. Lock the channel? `+lockvote yes`.",
            )
            self.store.questions["lockvote"] = {"votes": [], "at": int(time.time())}

    # -- membership -------------------------------------------------------
    def on_member_add(self, data: dict[str, Any]) -> None:
        user = data.get("user") or {}
        user_id = int(user.get("id", 0))
        if not user_id or user.get("bot"):
            return
        stats.bump("joins")
        if self.raid.hit():
            self.mod.set_channel_locked(MAIN_CHAT_ID, True)
            self.rest.send(
                MAIN_CHAT_ID,
                f"Raid pattern detected — {self.settings.raid_joins} joins in "
                f"{int(self.settings.raid_window)}s. Channel locked.",
            )
            stats.bump("raids")
        if self.store.snapshots.get(str(user_id)):
            added, _ = self.mod.restore(user_id)
            if added:
                log.info("restored %s role(s) to returning member %s", len(added), user_id)

    def on_member_remove(self, data: dict[str, Any]) -> None:
        user_id = int((data.get("user") or {}).get("id", 0))
        if user_id:
            self._member_roles.pop(user_id, None)

    def on_ban_add(self, data: dict[str, Any]) -> None:
        target = int((data.get("user") or {}).get("id", 0))
        if not target or not self.settings.anti_ban or target in self.settings.keep_banned:
            return
        if target in self.store.known_bans:
            return
        if self.rest.unban(GUILD_ID, target, "anti-ban (event)") in (200, 204):
            stats.bump("unbans")
            self.rest.send(
                MAIN_CHAT_ID,
                f"<@{target}> was banned. Anti-ban reversed it — that ban did not "
                f"come from this bot.",
            )
            log.warning("anti-ban reversed event ban on %s", target)

    def _hydrate_content(self, channel_id: int, message_id: int) -> str | None:
        try:
            row = self.rest.request("GET", f"/channels/{channel_id}/messages/{message_id}")
        except RestError as exc:
            log.debug("content hydrate failed: %s", exc)
            return None
        return (row or {}).get("content")

    def roles_for(self, user_id: int, member: dict | None) -> set[int]:
        if member and "roles" in member:
            return {int(r) for r in member["roles"]}
        cached = self._member_roles.get(user_id)
        if cached is not None:
            return cached
        fetched = self.rest.member(GUILD_ID, user_id)
        roles = {int(r) for r in (fetched or {}).get("roles", [])}
        self._member_roles[user_id] = roles
        return roles

    # -- dispatch ---------------------------------------------------------
    def dispatch(self, command: Command, user_id: int, message_id: int,
                 channel_id: int, roles: set[int]) -> None:
        spec = self.registry.resolve(command.name)
        if spec is None:
            suggestion = self.registry.suggest(command.name)
            hint = f" Did you mean `{PREFIX}{suggestion}`?" if suggestion else ""
            self.rest.reply(channel_id, message_id, f"Unknown command.{hint}")
            return
        if TIER_ORDER[self.tier_of(user_id, roles)] > TIER_ORDER[spec.tier]:
            self.rest.reply(channel_id, message_id, "You do not have permission for that.")
            stats.bump("denied")
            return
        key = (user_id, spec.name)
        now = time.time()
        if spec.cooldown and now - self._cooldowns.get(key, 0) < spec.cooldown:
            return
        self._cooldowns[key] = now
        try:
            spec.handler(command, user_id, message_id, channel_id, roles)
            stats.bump("commands")
        except RestError as exc:
            log.error("command %s failed: %s", spec.name, exc)
            self.rest.reply(channel_id, message_id, f"That failed ({exc.status}).")

    # -- shared helpers for cmd_impl --------------------------------------
    def reply(self, channel_id: int, message_id: int, body: str) -> None:
        self.rest.reply(channel_id, message_id, body)

    def send(self, channel_id: int, body: str, **extra) -> None:
        self.rest.send(channel_id, body, **extra)

    @staticmethod
    def target(command: Command) -> int | None:
        return user_id_from(command.args[0]) if command.args else None
