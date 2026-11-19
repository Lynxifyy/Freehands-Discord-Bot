"""Temporary ownership.

Lynx can lend someone operator authority for ten minutes with
`+Temp Ownership @user`. The grant is stored with its deadline, so a restart
does not make it permanent: `Engine.tier_of` consults `active()` and the role is
removed by a sweeper when the deadline passes.

Two things are deliberately explicit rather than assumed:

* the bot cannot grant a role above itself, so the grant is `Co owner` (the
  highest assignable role that carries Administrator). `Owner👑` sits above the
  bot and would be rejected by Discord.
* only one grant can be live at a time, and the role is always taken back
  before another is handed out, so a lost grant cannot leak authority.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .config import BOT_ID, GUILD_ID, LYNX_ID, ROLE_CO_OWNER
from .log import log, stats
from .rest import Rest, RestError

DEFAULT_MINUTES = 10


@dataclass
class Grant:
    user_id: int
    role_id: int
    expires_at: float
    granted_by: int

    @property
    def seconds_left(self) -> int:
        return max(0, int(self.expires_at - time.time()))

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at

    def to_json(self) -> dict:
        return {"user_id": self.user_id, "role_id": self.role_id,
                "expires_at": self.expires_at, "granted_by": self.granted_by}

    @classmethod
    def from_json(cls, data: dict) -> "Grant":
        return cls(int(data["user_id"]), int(data["role_id"]),
                   float(data["expires_at"]), int(data.get("granted_by", 0)))


class TempOwnership:
    def __init__(self, rest: Rest, store) -> None:
        self.rest = rest
        self.store = store
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._grant: Grant | None = None
        self._loaded = False

    # -- state ------------------------------------------------------------
    @property
    def grant(self) -> Grant | None:
        """The live grant object.

        Cached rather than rebuilt on each access so a caller can adjust the
        deadline, and so the stored JSON is the single source of truth across a
        restart.
        """
        if not self._loaded:
            raw = self.store.settings.temp_grant
            try:
                self._grant = Grant.from_json(raw) if raw else None
            except (KeyError, TypeError, ValueError):
                self._grant = None
            self._loaded = True
        return self._grant

    def _save(self, grant: Grant | None) -> None:
        self._grant = grant
        self._loaded = True
        self.store.settings.temp_grant = grant.to_json() if grant else None
        self.store.save(force=True)

    def active(self, user_id: int) -> bool:
        """True while `user_id` holds a live temporary ownership grant."""
        grant = self.grant
        return bool(grant and grant.user_id == user_id and not grant.expired)

    # -- granting ---------------------------------------------------------
    def grant_to(self, user_id: int, minutes: int = DEFAULT_MINUTES,
                 granted_by: int = LYNX_ID) -> tuple[bool, str]:
        if user_id == BOT_ID:
            return False, "I cannot own the server."
        if user_id in (LYNX_ID,):
            return False, "You already own it."
        if minutes <= 0:
            return False, "The duration must be at least a minute."

        with self._lock:
            previous = self.grant
            if previous:
                self._revoke(previous, reason="replaced by a new grant")

            status = self.rest.add_role(GUILD_ID, user_id, ROLE_CO_OWNER,
                                        reason=f"temporary ownership ({minutes}m)")
            if status not in (200, 204):
                log.warning("temp ownership grant failed for %s (status %s)",
                            user_id, status)
                return False, (
                    f"Discord refused the role ({status}). The bot can only assign "
                    f"roles below its own position."
                )

            grant = Grant(user_id, ROLE_CO_OWNER, time.time() + minutes * 60, granted_by)
            self._save(grant)
            stats.bump("temp_ownership")
            log.info("temporary ownership granted to %s for %dm", user_id, minutes)
            return True, f"<@{user_id}> is now a temporary owner for {minutes} minutes."

    def _revoke(self, grant: Grant, reason: str = "temporary ownership expired") -> bool:
        status = self.rest.remove_role(GUILD_ID, grant.user_id, grant.role_id, reason=reason)
        ok = status in (200, 204)
        if not ok:
            log.warning("could not remove temporary ownership from %s (status %s)",
                        grant.user_id, status)
        self._save(None)
        return ok

    def revoke(self, reason: str = "temporary ownership revoked") -> tuple[bool, str]:
        with self._lock:
            grant = self.grant
            if not grant:
                return False, "Nobody holds temporary ownership."
            ok = self._revoke(grant, reason)
            stats.bump("temp_ownership_revoked")
            if ok:
                return True, f"Temporary ownership removed from <@{grant.user_id}>."
            return False, (
                f"Discord refused to remove the role from <@{grant.user_id}>. "
                f"Remove it by hand."
            )

    # -- expiry -----------------------------------------------------------
    def sweep(self) -> Grant | None:
        """Revoke an expired grant. Returns the grant that was revoked."""
        grant = self.grant
        if not grant or not grant.expired:
            return None
        with self._lock:
            grant = self.grant
            if not grant or not grant.expired:
                return None
            self._revoke(grant)
            log.info("temporary ownership for %s expired", grant.user_id)
            return grant

    def start_sweeper(self, interval: float = 20.0) -> None:
        if self._thread and self._thread.is_alive():
            return

        def loop() -> None:
            while not self._stop.wait(interval):
                try:
                    revoked = self.sweep()
                except RestError as exc:
                    log.warning("temp ownership sweep failed: %s", exc)
                    continue
                if revoked:
                    self._announce(revoked)

        self._thread = threading.Thread(target=loop, name="temp-ownership", daemon=True)
        self._thread.start()
        log.info("temporary ownership sweeper started")

    def stop_sweeper(self) -> None:
        self._stop.set()

    def _announce(self, grant: Grant) -> None:
        from .config import MAIN_CHAT_ID

        try:
            self.rest.send(
                MAIN_CHAT_ID,
                f"Temporary ownership for <@{grant.user_id}> has ended.",
                allowed_mentions={"parse": [], "users": [str(grant.user_id)]},
            )
        except RestError as exc:
            log.warning("could not announce the expiry: %s", exc)
