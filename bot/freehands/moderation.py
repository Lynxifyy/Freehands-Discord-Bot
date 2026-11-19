"""Moderation primitives: role hierarchy, snapshots, anti-ban, lockdown.

Everything here is a method on `Moderator` so the rules live in one place and
the command layer only has to name the intent. Hierarchy is checked before
every write, because a silent 403 in the middle of a role strip is how an
incident turns into a mess.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .config import (
    GUILD_ID,
    ROLE_ETERNAL,
    Settings,
)
from .log import log, stats
from .rest import Rest, RestError
from .store import Store


@dataclass
class RoleInfo:
    id: int
    name: str
    position: int
    managed: bool
    permissions: int


class Moderator:
    def __init__(self, rest: Rest, store: Store, settings: Settings) -> None:
        self.rest = rest
        self.store = store
        self.settings = settings
        self.roles: dict[int, RoleInfo] = {}
        self.bot_top = 0

    # -- guild metadata ---------------------------------------------------
    def refresh_roles(self, bot_role_ids: set[int] | None = None) -> None:
        payload = self.rest.request("GET", f"/guilds/{GUILD_ID}/roles") or []
        self.roles = {
            int(r["id"]): RoleInfo(
                id=int(r["id"]),
                name=r["name"],
                position=int(r["position"]),
                managed=bool(r.get("managed")),
                permissions=int(r.get("permissions", 0)),
            )
            for r in payload
        }
        if bot_role_ids:
            self.bot_top = max(
                (self.roles[r].position for r in bot_role_ids if r in self.roles), default=0
            )

    def manageable(self, role_id: int) -> bool:
        role = self.roles.get(role_id)
        if role is None:
            return False
        return not role.managed and role.position < self.bot_top

    def role_name(self, role_id: int) -> str:
        role = self.roles.get(role_id)
        return role.name if role else str(role_id)

    # -- snapshots --------------------------------------------------------
    def snapshot(self, user_id: int) -> list[int] | None:
        member = self.rest.member(GUILD_ID, user_id)
        if not member:
            return None
        roles = [int(r) for r in member.get("roles", [])]
        self.store.snapshots[str(user_id)] = roles
        self.store.touch()
        return roles

    def restore(self, user_id: int, extra: tuple[int, ...] = ()) -> tuple[list[str], list[str]]:
        wanted = list(self.store.snapshots.get(str(user_id), []))
        wanted.extend(r for r in extra if r not in wanted)
        added, failed = [], []
        for role_id in wanted:
            if not self.manageable(role_id):
                continue
            if self.rest.add_role(GUILD_ID, user_id, role_id, "role restore") in (200, 204):
                added.append(self.role_name(role_id))
            else:
                failed.append(self.role_name(role_id))
        return added, failed

    def strip_roles(self, user_id: int, keep: tuple[int, ...] = (ROLE_ETERNAL,)) -> tuple[list[str], list[str]]:
        member = self.rest.member(GUILD_ID, user_id)
        if not member:
            return [], ["member not found"]
        removed, skipped = [], []
        for raw in member.get("roles", []):
            role_id = int(raw)
            if role_id in keep:
                skipped.append(self.role_name(role_id))
                continue
            if not self.manageable(role_id):
                skipped.append(f"{self.role_name(role_id)} (above bot)")
                continue
            if self.rest.remove_role(GUILD_ID, user_id, role_id, "role strip") in (200, 204):
                removed.append(self.role_name(role_id))
            else:
                skipped.append(f"{self.role_name(role_id)} (failed)")
        return removed, skipped

    # -- bankruptcy -------------------------------------------------------
    def bankrupt(self, user_id: int, actor_id: int) -> tuple[list[str], list[str], list[int]]:
        """Strip every manageable role and remember what was taken.

        Returns (removed, kept, stored_ids). `kept` is what the bot could not
        touch - a role above it, or an integration-managed role - and those are
        deliberately not stored, so a recovery never invents a role the member
        did not have.
        """
        member = self.rest.member(GUILD_ID, user_id)
        if not member:
            return [], ["member not found"], []
        taken: list[int] = []
        removed: list[str] = []
        kept: list[str] = []
        for raw in member.get("roles", []):
            role_id = int(raw)
            if role_id == ROLE_ETERNAL:
                kept.append(self.role_name(role_id))
                continue
            if not self.manageable(role_id):
                kept.append(f"{self.role_name(role_id)} (above bot)")
                continue
            if self.rest.remove_role(GUILD_ID, user_id, role_id, "bankrupt") in (200, 204):
                removed.append(self.role_name(role_id))
                taken.append(role_id)
            else:
                kept.append(f"{self.role_name(role_id)} (failed)")

        # An empty record would make a later recovery claim it restored
        # something, so only remember a strip that actually took a role.
        if taken:
            self.store.bankrupt[str(user_id)] = {
                "roles": taken,
                "by": actor_id,
                "at": time.time(),
                "names": removed,
            }
            self.store.touch()
            self.store.save(force=True)
        return removed, kept, taken

    def unbankrupt(self, user_id: int) -> tuple[list[str], list[str]]:
        """Give back exactly the roles the last bankruptcy took."""
        record = self.store.bankrupt.pop(str(user_id), None)
        if not record:
            return [], ["no bankruptcy on record"]
        added: list[str] = []
        failed: list[str] = []
        for role_id in record.get("roles", []):
            if not self.manageable(role_id):
                failed.append(f"{self.role_name(role_id)} (above bot)")
                continue
            if self.rest.add_role(GUILD_ID, user_id, role_id, "bankruptcy recovery") in (200, 204):
                added.append(self.role_name(role_id))
            else:
                failed.append(self.role_name(role_id))
        self.store.touch()
        self.store.save(force=True)
        return added, failed

    # -- anti-ban ---------------------------------------------------------
    def ban_list(self) -> dict[int, str]:
        try:
            payload = self.rest.bans(GUILD_ID)
        except RestError as exc:
            log.warning("ban list failed: %s", exc)
            return {}
        return {int(row["user"]["id"]): row["user"].get("username", "?") for row in payload}

    def anti_ban_sweep(self, reverse_only: bool = False) -> list[int]:
        """Lift bans, skipping the keep-banned exceptions.

        `reverse_only` limits the sweep to bans that appeared after startup,
        which is what the audit-log path wants.
        """
        lifted = []
        for user_id, username in self.ban_list().items():
            if user_id in self.settings.keep_banned:
                continue
            if reverse_only and user_id in self.store.known_bans:
                continue
            if self.rest.unban(GUILD_ID, user_id, "anti-ban") in (200, 204):
                lifted.append(user_id)
                stats.bump("unbans")
                log.warning("anti-ban lifted ban on %s (%s)", username, user_id)
        return lifted

    def seed_known_bans(self) -> None:
        self.store.known_bans = set(self.ban_list())
        self.store.touch()

    def enforce_keep_banned(self) -> list[int]:
        if not self.settings.keep_banned:
            return []
        current = self.ban_list()
        applied = []
        for user_id in sorted(self.settings.keep_banned):
            if user_id in current:
                continue
            if self.rest.ban(GUILD_ID, user_id, "keep-banned") in (200, 204):
                applied.append(user_id)
                log.info("keep-banned re-applied ban on %s", user_id)
        return applied

    def new_bans_from_audit(self, limit: int = 15) -> list[tuple[int, int]]:
        """(target_id, moderator_id) for bans newer than the last check."""
        seen_before = set(self.store.known_bans)
        found: list[tuple[int, int]] = []
        for entry in self.rest.audit(GUILD_ID, 22, limit=limit):
            target = str(entry.get("target_id") or "")
            moderator = str(entry.get("user_id") or "")
            if not target.isdigit():
                continue
            target_id = int(target)
            if target_id in seen_before:
                continue
            found.append((target_id, int(moderator) if moderator.isdigit() else 0))
        return found

    # -- channel state ----------------------------------------------------
    def set_channel_locked(self, channel_id: int, locked: bool) -> bool:
        overwrite = {"send_messages": False if locked else None}
        status, _ = self.rest.try_request(
            "PUT",
            f"/channels/{channel_id}/permissions/{GUILD_ID}",
            {"type": 0, "allow": "0", "deny": "2048" if locked else "0"},
        )
        if status in (200, 204):
            self.settings.lockdown = locked
            self.store.touch()
        return status in (200, 204)

    def mute_everyone(self, role_id: int = ROLE_ETERNAL, mute: bool = True) -> bool:
        status, _ = self.rest.try_request(
            "PATCH",
            f"/guilds/{GUILD_ID}/roles/{role_id}",
            {"permissions": "0" if mute else None} if mute else {},
        )
        if mute:
            status, _ = self.rest.try_request(
                "PATCH",
                f"/channels/{GUILD_ID}/permissions/{role_id}",
                {"type": 0, "allow": "0", "deny": "2048"},
            )
        return status in (200, 204)

    # -- helpers ----------------------------------------------------------
    def is_higher(self, actor_id: int, target_id: int) -> bool:
        if actor_id == GUILD_ID:
            return False
        actor = self.rest.member(GUILD_ID, actor_id)
        target = self.rest.member(GUILD_ID, target_id)
        if not actor or not target:
            return True
        def top(member):
            positions = [self.roles[int(r)].position for r in member.get("roles", [])
                         if int(r) in self.roles]
            return max(positions, default=0)
        return top(actor) > top(target)
