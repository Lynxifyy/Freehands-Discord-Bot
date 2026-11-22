"""Event routing, auto-moderation and command dispatch.

`Engine.handle_event` is the single entry point for both the gateway and the
poll fallback, so behaviour cannot diverge between transports.
"""

from __future__ import annotations

import os
import time
from typing import Any

from . import text
from .codebook import EYES, SIREN, Codebook, render_alert
from .commands import Command, Registry, parse, user_id_from
from .config import (
    ARCEUS_ID,
    BOT_ID,
    CODE8_MEMBERS,
    GUILD_ID,
    LYNX_ID,
    DYLLAN_ID,
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
from .ops import AlertRoom, OpsChannel
from .tempown import TempOwnership
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
        self.ops = OpsChannel(rest, store)
        self.rooms: dict[int, AlertRoom] = {}
        self.tempown = TempOwnership(rest, store)
        if self.ops.channel_id:
            self.channels.add(self.ops.channel_id)
        for cid in (store.settings.room_channels or {}).values():
            self.channels.add(int(cid))
        from . import cmd_impl  # local import keeps the registry wiring in one place

        cmd_impl.register(self)

    # -- identity ---------------------------------------------------------
    def tier_of(self, user_id: int, roles: set[int]) -> str:
        if user_id in (OWNER_ID, LYNX_ID, ARCEUS_ID):
            return "owner"
        if self.tempown.active(user_id):
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

        # An alert room is a private channel with a fixed member list. Anyone
        # else is evicted before they can speak, exactly like the ops channel.
        if channel_id in self.rooms or channel_id in self._room_ids():
            room = self.rooms.get(channel_id) or self._room_for(channel_id)
            if room is not None:
                if not room.allows(user_id):
                    self.evict_intruder(user_id, content, channel_id, author, room=room)
                    return
                command = parse(content)
                if command:
                    self.dispatch(command, user_id, message_id, channel_id, roles)
                return

        # The ops channel is checked before anything else: a non-operator must
        # not be able to run a command or raise a code from inside it.
        if channel_id == self.ops.channel_id:
            if not self.ops.allows(user_id):
                self.evict_intruder(user_id, content, channel_id, author)
                return
            command = parse(content)
            if command:
                self.dispatch(command, user_id, message_id, channel_id, roles)
            return

        self.watch_screen(user_id, content, message_id, channel_id, author)

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

    # -- alert rooms ------------------------------------------------------
    def _room_ids(self) -> set[int]:
        return {int(c) for c in (self.settings.room_channels or {}).values()}

    def _room_for(self, channel_id: int) -> AlertRoom | None:
        """Rebuild a room handle after a restart from the persisted record."""
        for name, cid in (self.settings.room_channels or {}).items():
            if int(cid) != channel_id:
                continue
            room = AlertRoom(self.rest, self.store, self._room_members(name))
            if room.load(name):
                self.rooms[channel_id] = room
                return room
        return None

    @staticmethod
    def _room_members(name: str) -> frozenset[int]:
        # Code 8 rooms are the only ones today; the name carries the code so a
        # later room type can pick a different list without touching routing.
        return CODE8_MEMBERS

    def open_alert_room(self, code: int, opened_by: int) -> AlertRoom | None:
        room = AlertRoom(self.rest, self.store, self._room_members(str(code)))
        channel_id = room.open(code, opened_by)
        if not channel_id:
            return None
        self.rooms[channel_id] = room
        self.channels.add(channel_id)
        return room

    # -- ops channel ------------------------------------------------------
    def evict_intruder(self, user_id: int, content: str, channel_id: int,
                       author: dict, room=None) -> None:
        """A non-member posted in a private channel.

        Order matters: revoke access and clear their messages first, then tell
        the operators, so the notice cannot be read by the person being removed.
        """
        target_room = room or self.ops
        result = target_room.evict(user_id)
        name = author.get("username") or str(user_id)
        lines = [
            f"{SIREN} **Unauthorised access** - <@{user_id}> (`{name}`) posted here.",
            "",
            f"**Access revoked** {'yes' if result.removed else 'FAILED - a role above the bot grants it'}",
            f"**Messages removed** {result.purged}",
        ]
        if content:
            lines += ["", f"**They said** {content[:500]}"]
        if not result.removed:
            lines += [
                "",
                "_Escalating to a kick, which needs no permission hierarchy._",
            ]
            status = self.rest.kick(GUILD_ID, user_id, reason="entered a private channel")
            lines.append(f"**Kick** {'sent' if status in (200, 204) else f'failed ({status})'}")
        target_room.post("\n".join(lines))
        self.store.add_incident({
            "at": int(time.time()), "code": 0, "title": "ops intrusion",
            "by": user_id, "trigger": content[:120],
        })
        log.warning("non-operator %s posted in the ops channel", user_id)

    def ensure_ops(self, force_new: bool = False) -> int:
        channel_id = self.ops.ensure(force_new)
        self.channels.add(channel_id)
        return channel_id

    # -- Dyllan watch -----------------------------------------------------
    def arm_watch(self, armed: bool) -> None:
        self.settings.watch_armed = armed
        self.store.save(force=True)

    def watch_screen(self, user_id: int, content: str, message_id: int,
                     channel_id: int, author: dict) -> None:
        """Log and screen every message from the watched member."""
        if user_id != WATCH_ID or not self.settings.watch_enabled:
            return
        if not self.settings.watch_armed:
            return

        flags = text.screen(content)
        name = author.get("username") or str(user_id)
        lines = [f"{EYES} **Watch** - <@{user_id}> (`{name}`) in <#{channel_id}>"]
        if flags:
            lines.append(f"**Flags** {', '.join(flags)}")
        lines += ["", content[:900] or "_(empty or attachment only)_"]
        self.ops.post("\n".join(lines))
        stats.bump("watched")
        log.info("watched message from %s (flags: %s)", user_id, flags or "none")

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
        mentions = {
            "parse": [],
            "users": list(dict.fromkeys(users)),
            "roles": [str(r) for r in code.ping_roles],
        }
        if code.room:
            # Nothing at all goes to open chat. Naming a suspected spy where the
            # spy can read it is the one thing this code exists to avoid, so the
            # alert is confined to the room and the trigger message is removed.
            room = self.open_alert_room(code.number, user_id)
            if room is None:
                # The room could not be made. The alert must still reach the
                # operators, so fall back to the ops channel - never open chat.
                log.error("code %s room failed; falling back to the ops channel", code.number)
                if self.ops.channel_id:
                    self.ops.post(
                        body + "\n\n_Room creation failed - this alert is in the ops channel._",
                        allowed_users=[OWNER_ID, ARCEUS_ID, LYNX_ID],
                    )
            else:
                leak = room.leakers()
                if leak:
                    body += (
                        "\n\n**This room is not fully private.** These roles carry "
                        "Administrator, which overrides a channel deny, so every "
                        "holder can see this room: "
                        + ", ".join(f"`{name}`" for _, name in leak)
                        + ". Remove Administrator from them to make the room "
                        "four-people-only."
                    )
                room.post(body, allowed_users=[OWNER_ID, ARCEUS_ID, LYNX_ID])
            self.rest.delete(channel_id, message_id)
            self.rest.react(channel_id, message_id, code.emoji)
            self.store.add_incident({
                "at": int(time.time()),
                "code": code.number,
                "title": code.title,
                "by": user_id,
                "trigger": hit.matched_text,
            })
            stats.bump("codes")
            log.info("code %s (%s) raised by %s in a private room",
                     code.number, code.title, user_id)
            return True

        # Sensitive codes go to the private channel only; if it does not exist
        # yet the alert still has to land somewhere, so it falls back to open
        # chat with a note instead of disappearing.
        target = MAIN_CHAT_ID
        if code.ops and self.ops.channel_id:
            target = self.ops.channel_id
        elif code.ops:
            body += "\n\n_No ops channel yet - run `+ops create`._"
        try:
            self.rest.send(target, body, allowed_mentions=mentions)
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
        if code.arm_watch and self.settings.watch_enabled and not self.settings.watch_armed:
            self.arm_watch(True)
            self.ops.post(
                f"{EYES} **Watch armed** - <@{WATCH_ID}> is now logged to this channel."
            )
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
        """Timeout Dyllan on request. Targets Dyllan explicitly, not the watch
        target: `is_punish_request` only fires on his aliases, and pointing the
        watch elsewhere must not move who this punishes."""
        if not self.is_operator(user_id, roles):
            return
        count = self.store.strike(DYLLAN_ID, "punish")
        self.rest.timeout(GUILD_ID, DYLLAN_ID, 3600, "punish request")
        self.rest.reply(
            channel_id, message_id, f"Punishment {count} applied to <@{DYLLAN_ID}> (1h)."
        )
        if count >= self.settings.punish_strikes_to_lock:
            self.rest.send(
                channel_id,
                f"<@{OWNER_ID}> <@{ARCEUS_ID}> <@{LYNX_ID}> — <@{DYLLAN_ID}> has hit "
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
        if spec.only_user is not None and user_id != spec.only_user:
            self.rest.reply(channel_id, message_id, "Only Lynx can run that command.")
            stats.bump("denied")
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
