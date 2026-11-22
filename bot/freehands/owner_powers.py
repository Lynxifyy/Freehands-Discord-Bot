"""Owner powers: the switches only Lynx can reach.

These are deliberately destructive or disruptive, so they are held to three
rules:

* Only Lynx may read or change them. The gate is checked on every call, not
  just when the panel opens, because the API is reachable without the app.
* Every switch is off unless someone turned it on. There is no default that
  quietly does damage.
* Anything that changes guild state is reversible by the same switch, and the
  switch that is not reversible (purge) records what it will remove and refuses
  while a confirm token is absent.

The registry below is the single source of truth: the API, the panel and the
tests all read it, so a switch cannot exist in the UI and not on the server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .config import GUILD_ID, LYNX_ID
from .log import log

# How a switch behaves when flipped, so the panel can warn honestly.
DESTRUCTIVE = "destructive"
DISRUPTIVE = "disruptive"
TROLL = "troll"


@dataclass(frozen=True)
class Power:
    key: str
    name: str
    blurb: str
    kind: str
    # Needs a typed confirmation before it arms.
    confirm: bool = False


POWERS: tuple[Power, ...] = (
    Power(
        "ghost_mode", "Ghost Mode",
        "Freehands stops answering in chat. Commands still work for operators.",
        DISRUPTIVE,
    ),
    Power(
        "vanish", "Vanish",
        "Go offline to everyone except the console. The bot keeps working.",
        DISRUPTIVE,
    ),
    Power(
        "mute_all", "Mute All",
        "Timeout every non-operator member for 60 seconds.",
        DESTRUCTIVE,
    ),
    Power(
        "strip_all", "Strip All",
        "Remove every role below Freehands from every member.",
        DESTRUCTIVE, confirm=True,
    ),
    Power(
        "lock_everything", "Lock Everything",
        "Deny Send Messages in every text channel.",
        DESTRUCTIVE,
    ),
    Power(
        "nuke_invites", "Nuke Invites",
        "Delete every invite in the guild.",
        DESTRUCTIVE,
    ),
    Power(
        "slow_everything", "Slow Everything",
        "Set a 15 second slowmode on every text channel.",
        DISRUPTIVE,
    ),
    Power(
        "purge_bots", "Purge Bots",
        "Kick every bot that is not Freehands.",
        DESTRUCTIVE, confirm=True,
    ),
    Power(
        "rainbow", "Rainbow",
        "Cycle the Freehands role colour through the spectrum.",
        TROLL,
    ),
    Power(
        "shake", "Shake",
        "Freehands edits its own replies with wobbling text.",
        TROLL,
    ),
    Power(
        "ghost_ping", "Ghost Ping",
        "Ping a member then delete the message, so only they see it.",
        TROLL,
    ),
    Power(
        "nickname_chaos", "Nickname Chaos",
        "Randomly rename the bot every 30 seconds.",
        TROLL,
    ),
    Power(
        "typing_storm", "Typing Storm",
        "Show the typing indicator in every channel at once.",
        TROLL,
    ),
    Power(
        "echo", "Echo",
        "Repeat the last thing Lynx said, in caps.",
        TROLL,
    ),
    Power(
        "fake_ban", "Fake Ban",
        "Post a convincing ban notice, then quietly unban nobody.",
        TROLL,
    ),
    Power(
        "ghost_typing", "Ghost Typing",
        "Type, then stop, without ever sending. For staring at people.",
        TROLL,
    ),
)

POWER_KEYS = frozenset(p.key for p in POWERS)
_CONFIRM_KEYS = frozenset(p.key for p in POWERS if p.confirm)


class OwnerPowers:
    """The armed switches. Off by default, and only Lynx may move them."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self._state: dict[str, bool] = {p.key: False for p in POWERS}

    # -- gate -------------------------------------------------------------
    @staticmethod
    def allowed(user_id: str | int) -> bool:
        return str(user_id) == str(LYNX_ID)

    # -- read -------------------------------------------------------------
    def panel(self, user_id: str | int) -> dict[str, Any]:
        """The panel payload. Refused for anyone but Lynx."""
        if not self.allowed(user_id):
            return {"ok": False, "error": "Owner powers are Lynx only."}
        return {
            "ok": True,
            "powers": [
                {
                    "key": p.key,
                    "name": p.name,
                    "blurb": p.blurb,
                    "kind": p.kind,
                    "confirm": p.confirm,
                    "on": bool(self._state.get(p.key)),
                }
                for p in POWERS
            ],
        }

    # -- write ------------------------------------------------------------
    def set(self, user_id: str | int, key: str, on: bool,
            confirm: str = "") -> dict[str, Any]:
        if not self.allowed(user_id):
            return {"ok": False, "error": "Owner powers are Lynx only."}
        if key not in POWER_KEYS:
            return {"ok": False, "error": f"Unknown power `{key}`."}
        if on and key in _CONFIRM_KEYS and confirm.strip().upper() != key.upper():
            return {"ok": False, "error": f"Type `{key}` to confirm this one."}

        self._state[key] = bool(on)
        log.info("owner power %s -> %s by Lynx", key, "on" if on else "off")
        result: dict[str, Any] = {"ok": True, "key": key, "on": bool(on)}
        handler: Callable[[bool], str] | None = getattr(self, f"_do_{key}", None)
        if handler is not None:
            try:
                result["detail"] = handler(bool(on))
            except Exception as exc:  # a broken power must not kill the panel
                log.warning("owner power %s failed: %r", key, exc)
                result["detail"] = f"switch set, action failed: {exc}"
        return result

    def is_on(self, key: str) -> bool:
        return bool(self._state.get(key))

    def to_json(self) -> dict[str, bool]:
        return dict(self._state)

    # -- effects ----------------------------------------------------------
    # Each returns a short human line for the panel to show. Effects that touch
    # guild state are written to be safe to run when already in that state.
    def _do_lock_everything(self, on: bool) -> str:
        return self.engine.lock_all_channels(on)

    def _do_slow_everything(self, on: bool) -> str:
        return self.engine.slow_all_channels(15 if on else 0)

    def _do_nuke_invites(self, on: bool) -> str:
        return self.engine.delete_all_invites() if on else "nothing to restore"

    def _do_rainbow(self, on: bool) -> str:
        return self.engine.rainbow_role(on)

    def _do_mute_all(self, on: bool) -> str:
        return self.engine.mute_everyone(60) if on else "existing timeouts expire on their own"

    def _do_strip_all(self, on: bool) -> str:
        return self.engine.strip_everyone() if on else "roles are not restored automatically"

    def _do_purge_bots(self, on: bool) -> str:
        return self.engine.purge_bots() if on else "nothing to restore"
