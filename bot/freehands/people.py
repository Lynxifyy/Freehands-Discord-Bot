"""Who can use Freehands, and how much power they hold.

The console shows a dropdown of the people a loop can be aimed at, labelled by
what they can actually do to the bot. The label is derived from the same rules
the dispatcher uses, so the list cannot drift from the real permissions.

Lynx is listed but not selectable. He owns Freehands, and a control panel that
can loop its own owner is a way to lose the bot. The refusal is enforced here
as well as in the UI, because the API is reachable without the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import (
    ALLOWED_OPS,
    ARCEUS_ID,
    LYNX_ID,
    MOD_ROLES,
    OPERATOR_ROLES,
    OWNER_ID,
    ROLE_ADMIN,
    ROLE_CO_OWNER,
    ROLE_HELPER,
    ROLE_MOD,
)

# Ordered strongest first. The label is what the dropdown shows beside a name.
TIERS = (
    ("owner", "Owner"),
    ("co-owner", "Co-owner"),
    ("admin", "Admin"),
    ("mod", "Moderator"),
    ("helper", "Helper"),
)

# A person holding any of these roles can run at least the mod commands.
ACCESS_ROLES = frozenset(OPERATOR_ROLES) | frozenset(MOD_ROLES)


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    display: str
    tier: str
    label: str
    avatar: str
    # Lynx owns Freehands, so no destructive action may target him.
    protected: bool = False
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display": self.display,
            "tier": self.tier,
            "label": self.label,
            "avatar": self.avatar,
            "protected": self.protected,
            "reason": self.reason,
        }


def avatar_url(user_id: str, avatar_hash: str = "") -> str:
    if avatar_hash:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=128"
    # Discord's default avatar index is (id >> 22) % 6 for the modern set.
    try:
        index = (int(user_id) >> 22) % 6
    except (TypeError, ValueError):
        index = 0
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


def tier_for(user_id: str, roles: set[int]) -> tuple[str, str]:
    """The (tier, label) a member holds. Mirrors `Engine.tier_of`."""
    uid = str(user_id)
    if uid == str(LYNX_ID):
        return "owner", "Owner of Freehands"
    if uid in (str(OWNER_ID), str(ARCEUS_ID)):
        return "owner", "Owner"
    if roles & set(OPERATOR_ROLES):
        if ROLE_CO_OWNER in roles:
            return "co-owner", "Co-owner"
        if ROLE_ADMIN in roles:
            return "admin", "Admin"
        return "owner", "Owner"
    if roles & set(MOD_ROLES):
        if ROLE_HELPER in roles and ROLE_MOD not in roles:
            return "helper", "Helper"
        return "mod", "Moderator"
    return "user", "User"


def _name_of(member: dict) -> tuple[str, str, str]:
    """(username, display name, avatar hash) from a guild member payload."""
    user = member.get("user") or {}
    username = str(user.get("username") or "")
    display = str(member.get("nick") or user.get("global_name") or username or "unknown")
    return username, display, str(user.get("avatar") or "")


def people(members: list[dict]) -> list[Person]:
    """Everyone who can reach the bot, strongest first.

    Only people with a tier above `user` are listed: a dropdown of every member
    in the guild is not a control panel, it is a directory.
    """
    rows: list[Person] = []
    seen: set[str] = set()
    for member in members:
        user = member.get("user") or {}
        uid = str(user.get("id") or "")
        if not uid or uid in seen or user.get("bot"):
            continue
        roles = {int(r) for r in (member.get("roles") or []) if str(r).isdigit()}
        tier, label = tier_for(uid, roles)
        if tier == "user" and uid not in {str(i) for i in ALLOWED_OPS}:
            continue
        seen.add(uid)
        username, display, avatar_hash = _name_of(member)
        protected = uid == str(LYNX_ID)
        rows.append(Person(
            id=uid,
            name=username or display,
            display=display or username,
            tier=tier,
            label=label,
            avatar=avatar_url(uid, avatar_hash),
            protected=protected,
            reason="Owns Freehands" if protected else "",
        ))

    order = {tier: i for i, (tier, _) in enumerate(TIERS)}
    rows.sort(key=lambda p: (order.get(p.tier, 9), p.display.lower()))
    return rows


def can_target(target_id: str) -> tuple[bool, str]:
    """Whether a destructive action may name this member."""
    if str(target_id) == str(LYNX_ID):
        return False, "Lynx owns Freehands"
    return True, ""
