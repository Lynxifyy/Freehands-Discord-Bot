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
    OPS_ACCESS_ROLE_NAME,
    OPS_CHANNEL_NAME,
    OPS_CHANNEL_TOPIC,
)
from .log import log, stats
from .rest import Rest, RestError

VIEW_CHANNEL = 1 << 10
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
    admins: list[int]      # hold Administrator: overwrites cannot hide anything
    missing: list[int]     # on the allow-list but not granted access yet


class OpsChannel:
    def __init__(self, rest: Rest, store) -> None:
        self.rest = rest
        self.store = store
        self.channel_id: int = int(store.settings.ops_channel_id or 0)
        self.role_id: int = int(store.settings.ops_role_id or 0)

    # -- lifecycle --------------------------------------------------------
    def ensure(self, force_new: bool = False) -> int:
        """Find or create the channel and its access role, then lock it down."""
        self._ensure_role()
        if not force_new and self.channel_id and self.rest.channel(self.channel_id):
            self._lock()
            self._grant_role()
            return self.channel_id

        found = self._find()
        if found and not force_new:
            self.channel_id = found
        else:
            self.channel_id = self._create()
        self.store.settings.ops_channel_id = self.channel_id
        self.store.save(force=True)
        self._lock()
        self._grant_role()
        return self.channel_id

    def _ensure_role(self) -> int:
        """Create the access role if missing. Deny-only, so it grants nothing."""
        if self.role_id and any(int(r["id"]) == self.role_id
                                for r in self.rest.request("GET", f"/guilds/{GUILD_ID}/roles")):
            return self.role_id
        for row in self.rest.request("GET", f"/guilds/{GUILD_ID}/roles") or []:
            if row["name"] == OPS_ACCESS_ROLE_NAME:
                self.role_id = int(row["id"])
                self.store.settings.ops_role_id = self.role_id
                return self.role_id
        try:
            row = self.rest.request(
                "POST", f"/guilds/{GUILD_ID}/roles",
                {"name": OPS_ACCESS_ROLE_NAME, "permissions": "0",
                 "mentionable": False, "hoist": False, "color": 0},
                reason="private operator channel gate",
            )
        except RestError as exc:
            log.error("could not create the ops access role: %s", exc)
            return 0
        self.role_id = int(row["id"])
        self.store.settings.ops_role_id = self.role_id
        self.store.save(force=True)
        log.info("ops access role created: %s", self.role_id)
        return self.role_id

    def _grant_role(self) -> None:
        for user_id in sorted(ALLOWED_OPS):
            status = self.rest.add_role(GUILD_ID, user_id, self.role_id,
                                        reason="ops channel access")
            if status not in (200, 204):
                log.warning("could not grant ops access to %s (status %s)", user_id, status)

    def _find(self) -> int:
        try:
            for row in self.rest.channels(GUILD_ID):
                if row.get("type") == 0 and row.get("name") == OPS_CHANNEL_NAME:
                    return int(row["id"])
        except RestError as exc:
            log.warning("channel lookup failed: %s", exc)
        return 0

    def _overwrites(self) -> list[dict]:
        """@everyone denied, the gate role allowed, the bot allowed.

        The gate role is the only path in. A per-member allow would let an
        Administrator through anyway, so it is not relied on for secrecy.
        """
        rows = [
            {"id": str(GUILD_ID), "type": TYPE_ROLE, "allow": "0", "deny": str(DENY)},
            {"id": str(BOT_ID), "type": TYPE_MEMBER, "allow": str(ALLOW), "deny": "0"},
        ]
        if self.role_id:
            rows.append({"id": str(self.role_id), "type": TYPE_ROLE,
                         "allow": str(ALLOW), "deny": "0"})
        return rows

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
        """Re-assert every overwrite. Cheap, idempotent, and the only thing
        standing between this channel and a manual permission edit."""
        if not self.channel_id:
            return
        ok = self.rest.put_overwrite(self.channel_id, GUILD_ID, TYPE_ROLE, "0", str(DENY),
                                     reason="ops channel lockdown")
        ok &= self.rest.put_overwrite(
            self.channel_id, BOT_ID, TYPE_MEMBER, str(ALLOW), "0",
            reason="ops channel allow-list",
        )
        if self.role_id:
            ok &= self.rest.put_overwrite(
                self.channel_id, self.role_id, TYPE_ROLE, str(ALLOW), "0",
                reason="ops channel gate role",
            )
        if ok not in (200, 204):
            log.warning("ops channel overwrites may be incomplete (status %s)", ok)

    # -- access -----------------------------------------------------------
    def allows(self, user_id: int) -> bool:
        return user_id in ALLOWED_OPS or user_id == BOT_ID

    def audit(self) -> Audit:
        """Report who can really see the channel.

        Discord's Administrator permission bypasses channel overwrites, so an
        admin who is not an operator can read this channel no matter what the
        overwrites say. There is no API to hide a channel from an admin; the
        only fix is to take that role away from them.
        """
        try:
            roles = self.rest.request("GET", f"/guilds/{GUILD_ID}/roles") or []
        except RestError as exc:
            log.warning("ops audit could not read roles: %s", exc)
            return Audit([], [], [])

        admin_roles = {int(r["id"]) for r in roles if int(r["permissions"]) & (1 << 3)}
        admins: list[int] = []
        # Members cannot be enumerated without the GUILD_MEMBERS intent, so the
        # known roles of the operators are all that can be checked directly.
        for user_id in sorted(ALLOWED_OPS):
            member = self.rest.member(GUILD_ID, user_id) or {}
            held = {int(r) for r in member.get("roles", [])}
            if held & admin_roles:
                admins.append(user_id)
        missing = []
        for user_id in sorted(ALLOWED_OPS):
            member = self.rest.member(GUILD_ID, user_id) or {}
            if self.role_id and self.role_id not in {int(r) for r in member.get("roles", [])}:
                missing.append(user_id)
        return Audit(sorted(ALLOWED_OPS), admins, missing)

    def evict(self, user_id: int, purge: bool = True) -> Intrusion:
        """Remove a non-operator's access and clear what they posted.

        A member-level deny loses to any role that grants the permission, so a
        failure here is reported rather than swallowed: the caller can then
        escalate to a kick.
        """
        # A member overwrite may not exist (access is role-gated), so removal is
        # best-effort; what matters is that they are not an operator.
        status = self.rest.delete_overwrite(self.channel_id, user_id,
                                            reason="not an operator")
        removed = status in (200, 204)
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
