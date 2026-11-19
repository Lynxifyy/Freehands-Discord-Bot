"""The private operator channel.

A code alert can be sensitive, so it does not belong in open chat. This module
owns one text channel whose permission overwrites deny `@everyone` and allow
only the owner, Arceus, Lynx and the bot itself.

Two things make it actually private rather than nominally private:

* the overwrites are re-asserted on every start and by `+ops lock`, so a manual
  permission edit does not quietly open the door, and
* every message in it is checked against the allow-list. Anyone who is not on
  the list has their overwrite deleted and their messages removed.

Discord refuses to remove a member's channel permission if a role above the bot
grants it, so the removal result is reported honestly instead of assumed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .config import (
    ALLOWED_OPS,
    BOT_ID,
    GUILD_ID,
    OPS_CHANNEL_NAME,
    OPS_CHANNEL_TOPIC,
    ROOM_CHANNEL_PREFIX,
)
from .log import log, stats
from .rest import Rest, RestError

VIEW_CHANNEL = 1 << 10
ADMINISTRATOR = 1 << 3
SEND_MESSAGES = 1 << 11
READ_MESSAGE_HISTORY = 1 << 16
ATTACH_FILES = 1 << 15
ADD_REACTIONS = 1 << 6

ALLOW = VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY | ATTACH_FILES | ADD_REACTIONS
DENY = VIEW_CHANNEL | SEND_MESSAGES

TYPE_ROLE = 0
TYPE_MEMBER = 1


@dataclass
class Intrusion:
    user_id: int
    removed: bool
    purged: int


@dataclass
class Audit:
    """Who can actually see the channel, and who only *thinks* they cannot."""
    allowed: list[int]
    missing: list[int]     # on the allow-list but cannot actually view


class Room:
    """A channel that exactly one set of members may see.

    Access is written as per-member overwrites and re-asserted on demand, so a
    manual permission edit cannot quietly open the door. `@everyone` is denied,
    no role is ever granted, and any overwrite outside the allow-list is
    deleted. `OpsChannel` and `AlertRoom` differ only in their member list.
    """

    def __init__(self, rest: Rest, store, members: frozenset[int]) -> None:
        self.rest = rest
        self.store = store
        self.members = members
        self.channel_id: int = 0

    # -- overwrites -------------------------------------------------------
    def _overwrites(self) -> list[dict]:
        """`@everyone` denied, then one allow row per member plus the bot.

        No role is involved. A gate role would be inherited by anyone handed it,
        and a role overwrite can beat a member overwrite, so membership is
        written per-user and nothing else is granted.
        """
        rows = [
            {"id": str(GUILD_ID), "type": TYPE_ROLE, "allow": "0", "deny": str(DENY)},
            {"id": str(BOT_ID), "type": TYPE_MEMBER, "allow": str(ALLOW), "deny": "0"},
        ]
        for user_id in sorted(self.members):
            rows.append({"id": str(user_id), "type": TYPE_MEMBER,
                         "allow": str(ALLOW), "deny": "0"})
        return rows

    def _lock(self) -> None:
        """Force the channel back to exactly the allowed members."""
        if not self.channel_id:
            return
        ok = self.rest.put_overwrite(self.channel_id, GUILD_ID, TYPE_ROLE, "0", str(DENY),
                                     reason="room lockdown")
        for user_id in sorted(self.members | {BOT_ID}):
            ok &= self.rest.put_overwrite(
                self.channel_id, user_id, TYPE_MEMBER, str(ALLOW), "0",
                reason="room allow-list",
            )
        if ok not in (200, 204):
            log.warning("room %s overwrites may be incomplete (status %s)",
                        self.channel_id, ok)
        self._strip_strays()

    def _strip_strays(self) -> int:
        """Delete every overwrite that is not the allow-list or @everyone."""
        rows = self.rest.channel(self.channel_id) or {}
        keep = {GUILD_ID, BOT_ID} | set(self.members)
        removed = 0
        for row in rows.get("permission_overwrites", []):
            target = int(row["id"])
            if target in keep:
                continue
            if self.rest.delete_overwrite(self.channel_id, target,
                                          reason="not on the allow-list") in (200, 204):
                removed += 1
                log.info("stripped stray overwrite for %s in %s", target, self.channel_id)
        return removed

    # -- access -----------------------------------------------------------
    def allows(self, user_id: int) -> bool:
        return user_id in self.members or user_id == BOT_ID

    def can_view(self, user_id: int, held: set[int] | None = None) -> bool:
        """Resolve whether a member can really view this channel.

        Discord's own resolution: union the base permissions, short-circuit on
        Administrator, then apply the @everyone overwrite, the member's role
        overwrites and finally any member overwrite. Without this the bot would
        have to trust a DELETE that succeeds even when nothing was there.
        """
        if not self.channel_id:
            return False
        try:
            roles = {int(r["id"]): r for r in
                     self.rest.request("GET", f"/guilds/{GUILD_ID}/roles") or []}
        except RestError as exc:
            log.warning("permission check could not read roles: %s", exc)
            return True  # fail closed: assume they can see it
        if held is None:
            member = self.rest.member(GUILD_ID, user_id) or {}
            held = {int(r) for r in member.get("roles", [])}

        base = int(roles.get(GUILD_ID, {}).get("permissions", 0))
        for role_id in held:
            if role_id in roles:
                base |= int(roles[role_id]["permissions"])
        if base & ADMINISTRATOR:
            return True

        rows = self.rest.channel(self.channel_id) or {}
        overwrites = {int(o["id"]): o for o in rows.get("permission_overwrites", [])}
        everyone = overwrites.get(GUILD_ID)
        if everyone:
            base = (base & ~int(everyone["deny"])) | int(everyone["allow"])
        for role_id in held:
            row = overwrites.get(role_id)
            if row and row.get("type") == TYPE_ROLE:
                base = (base & ~int(row["deny"])) | int(row["allow"])
        member_row = overwrites.get(user_id)
        if member_row and member_row.get("type") == TYPE_MEMBER:
            base = (base & ~int(member_row["deny"])) | int(member_row["allow"])
        return bool(base & VIEW_CHANNEL)

    def leakers(self) -> list[tuple[int, str]]:
        """Roles that let people who are NOT on the allow-list view this channel.

        A channel overwrite cannot beat the Administrator permission, so any
        role carrying it makes the room visible to everyone holding that role
        no matter what is denied here. That is a real hole in "only these four
        people can see it" and the operator has to close it in role settings -
        the bot cannot, because it cannot edit a role above itself. Returned as
        (role_id, role_name) so the warning can name them.
        """
        try:
            roles = self.rest.request("GET", f"/guilds/{GUILD_ID}/roles") or []
        except RestError as exc:
            log.warning("leaker audit could not read roles: %s", exc)
            return []
        # The bot's own roles do not leak the room to anyone but the bot, so
        # listing them would be noise in a warning meant for the operators.
        bot_roles: set[int] = set()
        try:
            me = self.rest.me()
            member = self.rest.member(GUILD_ID, int(me["id"])) or {}
            bot_roles = {int(r) for r in member.get("roles", [])}
        except (RestError, KeyError, ValueError) as exc:
            log.warning("leaker audit could not read the bot's roles: %s", exc)

        out: list[tuple[int, str]] = []
        for row in roles:
            role_id = int(row["id"])
            if role_id in bot_roles:
                continue
            if int(row.get("permissions", 0)) & ADMINISTRATOR:
                out.append((role_id, row.get("name", str(role_id))))
        return sorted(out, key=lambda r: r[1].lower())

    def evict(self, user_id: int, purge: bool = True) -> Intrusion:
        """Remove a non-member's access and clear what they posted.

        A member-level deny loses to any role that grants the permission, so a
        failure here is reported rather than swallowed.
        """
        # Discord answers 200 to a DELETE even when no overwrite existed, so the
        # status proves nothing. Check whether they can still view the channel.
        status = self.rest.delete_overwrite(self.channel_id, user_id,
                                            reason="not on the allow-list")
        removed = not self.can_view(user_id)
        purged = 0
        if purge:
            purged = self._purge_from(user_id)
        if not removed:
            log.warning("could not revoke access for %s (status %s)", user_id, status)
        stats.bump("intrusions")
        log.info("evicted %s from %s (removed=%s, purged=%s)",
                 user_id, self.channel_id, removed, purged)
        return Intrusion(user_id, removed, purged)

    def _purge_from(self, user_id: int) -> int:
        """Delete recent messages by one member in this channel."""
        try:
            rows = self.rest.messages(self.channel_id, limit=100)
        except RestError as exc:
            log.warning("room purge failed: %s", exc)
            return 0
        deleted = 0
        for row in rows:
            if int((row.get("author") or {}).get("id", 0)) != user_id:
                continue
            if self.rest.delete(self.channel_id, int(row["id"])) in (200, 204):
                deleted += 1
        return deleted

    # -- reporting --------------------------------------------------------
    def post(self, content: str, allowed_users=()) -> dict | None:
        if not self.channel_id:
            return None
        try:
            return self.rest.send(
                self.channel_id, content,
                allowed_mentions={"parse": [], "users": [str(u) for u in allowed_users]},
            )
        except RestError as exc:
            log.error("room post failed: %s", exc)
            return None


class OpsChannel(Room):
    def __init__(self, rest: Rest, store) -> None:
        super().__init__(rest, store, ALLOWED_OPS)
        self.channel_id: int = int(store.settings.ops_channel_id or 0)

    # -- lifecycle --------------------------------------------------------
    def ensure(self, force_new: bool = False) -> int:
        """Find or create the channel, then force the allow-list."""
        if not force_new and self.channel_id and self.rest.channel(self.channel_id):
            self._lock()
            return self.channel_id

        found = self._find()
        if found and not force_new:
            self.channel_id = found
        else:
            self.channel_id = self._create()
        self.store.settings.ops_channel_id = self.channel_id
        self.store.save(force=True)
        self._lock()
        return self.channel_id

    def _find(self) -> int:
        try:
            for row in self.rest.channels(GUILD_ID):
                if row.get("type") == 0 and row.get("name") == OPS_CHANNEL_NAME:
                    return int(row["id"])
        except RestError as exc:
            log.warning("channel lookup failed: %s", exc)
        return 0

    def _create(self) -> int:
        try:
            row = self.rest.create_channel(
                GUILD_ID, OPS_CHANNEL_NAME, 0, self._overwrites(),
                topic=OPS_CHANNEL_TOPIC, reason="private operator channel",
            )
        except RestError as exc:
            log.error("could not create the ops channel: %s", exc)
            raise
        log.info("ops channel created: #%s (%s)", OPS_CHANNEL_NAME, row["id"])
        return int(row["id"])

    # -- access -----------------------------------------------------------
    def audit(self) -> Audit:
        """Report which operators can actually view the channel.

        Members cannot be enumerated without the GUILD_MEMBERS intent, so this
        checks the allow-list rather than the whole guild.
        """
        missing = [u for u in sorted(ALLOWED_OPS) if not self.can_view(u)]
        return Audit(sorted(ALLOWED_OPS), missing)

    def describe(self) -> str:
        if not self.channel_id:
            return "no ops channel yet (run `+ops create`)"
        rows = self.rest.channel(self.channel_id) or {}
        name = rows.get("name", OPS_CHANNEL_NAME)
        return f"<#{self.channel_id}> (#{name})"


class AlertRoom(Room):
    """A one-shot private channel for a single sensitive code alert.

    Code 8 must not be announced in open chat, so instead of posting there the
    bot opens a room and moves the conversation into it. The member list is
    fixed at construction: the four people who are allowed to know, nobody else.

    Rooms are recorded in `settings.room_channels` so they can be found again
    after a restart. A room whose channel was deleted by hand is dropped from
    the record rather than reported as live.
    """

    def __init__(self, rest: Rest, store, members: frozenset[int],
                 prefix: str = ROOM_CHANNEL_PREFIX) -> None:
        super().__init__(rest, store, members)
        self.prefix = prefix

    # -- lifecycle --------------------------------------------------------
    def open(self, code: int, opened_by: int) -> int | None:
        """Create the room and return its id, or None if it could not be made."""
        name = f"{self.prefix}-{code}-{int(time.time())}"
        try:
            row = self.rest.create_channel(
                GUILD_ID, name, 0, self._overwrites(),
                topic=(f"Private alert room for code {code}. "
                       "Only the owner, Arceus, Lynx and Spy can see this."),
                reason=f"code {code} alert room",
            )
        except RestError as exc:
            log.error("could not create the alert room: %s", exc)
            return None
        self.channel_id = int(row["id"])
        self.store.settings.room_channels[name] = self.channel_id
        self.store.save(force=True)
        self._lock()
        log.info("alert room opened for code %s: %s (%s)", code, name, self.channel_id)
        stats.bump("rooms")
        return self.channel_id

    def close(self, reason: str = "alert resolved") -> bool:
        """Delete the room and forget it."""
        if not self.channel_id:
            return False
        status = self.rest.try_request(
            "DELETE", f"/channels/{self.channel_id}", reason=reason
        )[0]
        for name, cid in list(self.store.settings.room_channels.items()):
            if cid == self.channel_id:
                del self.store.settings.room_channels[name]
        self.store.save(force=True)
        log.info("alert room %s closed (status %s)", self.channel_id, status)
        self.channel_id = 0
        return status in (200, 204)

    def load(self, name: str) -> int | None:
        """Attach to a room recorded in settings, if its channel still exists."""
        cid = self.store.settings.room_channels.get(name)
        if not cid:
            return None
        if not self.rest.channel(cid):
            del self.store.settings.room_channels[name]
            self.store.save(force=True)
            return None
        self.channel_id = int(cid)
        return self.channel_id
