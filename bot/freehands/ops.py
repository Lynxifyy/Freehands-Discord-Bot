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


class OpsChannel:
    def __init__(self, rest: Rest, store) -> None:
        self.rest = rest
        self.store = store
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

    def _overwrites(self) -> list[dict]:
        """Exactly three members may see this channel: owner, Arceus, Lynx.

        No role is involved. A gate role would be inherited by anyone who is
        handed it, and a role overwrite also beats a member overwrite in some
        ordering, so membership is written per-user and nothing else is granted.
        The bot needs its own entry to post there.
        """
        rows = [
            {"id": str(GUILD_ID), "type": TYPE_ROLE, "allow": "0", "deny": str(DENY)},
            {"id": str(BOT_ID), "type": TYPE_MEMBER, "allow": str(ALLOW), "deny": "0"},
        ]
        for user_id in sorted(ALLOWED_OPS):
            rows.append({"id": str(user_id), "type": TYPE_MEMBER,
                         "allow": str(ALLOW), "deny": "0"})
        return rows

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

    def _lock(self) -> None:
        """Force the channel back to exactly the three allowed members.

        Re-asserted on every start and by `+ops lock`, so a manual grant is
        temporary. Any overwrite that is not the bot, one of the three, or
        @everyone is deleted - otherwise a stray grant would survive forever.
        """
        if not self.channel_id:
            return
        ok = self.rest.put_overwrite(self.channel_id, GUILD_ID, TYPE_ROLE, "0", str(DENY),
                                     reason="ops channel lockdown")
        for user_id in sorted(ALLOWED_OPS | {BOT_ID}):
            ok &= self.rest.put_overwrite(
                self.channel_id, user_id, TYPE_MEMBER, str(ALLOW), "0",
                reason="ops channel allow-list",
            )
        if ok not in (200, 204):
            log.warning("ops channel overwrites may be incomplete (status %s)", ok)
        self._strip_strays()

    def _strip_strays(self) -> int:
        """Delete every overwrite that is not the allow-list or @everyone."""
        rows = self.rest.channel(self.channel_id) or {}
        keep = {GUILD_ID, BOT_ID} | set(ALLOWED_OPS)
        removed = 0
        for row in rows.get("permission_overwrites", []):
            target = int(row["id"])
            if target in keep:
                continue
            if self.rest.delete_overwrite(self.channel_id, target,
                                          reason="not on the allow-list") in (200, 204):
                removed += 1
                log.info("stripped stray overwrite for %s", target)
        return removed

    # -- access -----------------------------------------------------------
    def allows(self, user_id: int) -> bool:
        return user_id in ALLOWED_OPS or user_id == BOT_ID

    def can_view(self, user_id: int, held: set[int] | None = None) -> bool:
        """Resolve whether a member can really view this channel.

        Discord's own resolution: union the base permissions, short-circuit on
        Administrator, then apply the @everyone overwrite, the member's role
        overwrites and finally any member overwrite. Without this the bot would
        have to trust a DELETE that succeeds even when nothing was there.
        """
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

    def audit(self) -> Audit:
        """Report which operators can actually view the channel.

        Members cannot be enumerated without the GUILD_MEMBERS intent, so this
        checks the allow-list rather than the whole guild.
        """
        missing = [u for u in sorted(ALLOWED_OPS) if not self.can_view(u)]
        return Audit(sorted(ALLOWED_OPS), missing)

    def evict(self, user_id: int, purge: bool = True) -> Intrusion:
        """Remove a non-operator's access and clear what they posted.

        A member-level deny loses to any role that grants the permission, so a
        failure here is reported rather than swallowed: the caller can then
        escalate to a kick.
        """
        # Discord answers 200 to a DELETE even when no overwrite existed, so the
        # status proves nothing. Check whether they can still view the channel.
        status = self.rest.delete_overwrite(self.channel_id, user_id,
                                            reason="not an operator")
        removed = not self.can_view(user_id)
        purged = 0
        if purge:
            purged = self._purge_from(user_id)
        if not removed:
            log.warning("could not revoke access for %s (status %s)", user_id, status)
        stats.bump("intrusions")
        log.info("evicted %s from the ops channel (removed=%s, purged=%s)",
                 user_id, removed, purged)
        return Intrusion(user_id, removed, purged)

    def _purge_from(self, user_id: int) -> int:
        """Delete recent messages by one member in the ops channel."""
        try:
            rows = self.rest.messages(self.channel_id, limit=100)
        except RestError as exc:
            log.warning("ops purge failed: %s", exc)
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
            log.error("ops post failed: %s", exc)
            return None

    def describe(self) -> str:
        if not self.channel_id:
            return "no ops channel yet (run `+ops create`)"
        rows = self.rest.channel(self.channel_id) or {}
        name = rows.get("name", OPS_CHANNEL_NAME)
        return f"<#{self.channel_id}> (#{name})"
