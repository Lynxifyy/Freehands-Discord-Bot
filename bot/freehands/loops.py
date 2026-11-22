"""Repeating ban and kick loops.

A loop is a moderation action that repeats on a timer. It exists for the case
a single ban cannot solve: a member who keeps rejoining, or a wave of alts that
needs clearing faster than a person can retype the command.

Two rules make it survivable, because an unbounded loop is a way to lose a
server:

* Every loop carries a maximum number of passes and a deadline. Whichever is
  reached first ends it. There is no "run forever" option.
* The protected ids - the owner and Lynx - are refused when the loop is armed
  and skipped again on every pass. A loop cannot be pointed at the owner of
  Freehands even if the arm call is forged.

Loops live in memory only. A restart cancels them, which is the safe direction:
a moderation action that resumes on its own after a crash is a surprise, and
the operator who armed it is not necessarily still watching.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .config import GUILD_ID, LYNX_ID, OWNER_ID
from .log import log

# Nobody can be looped, whoever asks. This is the one rule the console cannot
# override, because "ban the owner" has no undo once the bot loses its role.
IMMUNE = frozenset({OWNER_ID, LYNX_ID})


def is_immune(target: str | int) -> bool:
    """True when `target` is protected. Accepts the string form too, because a
    user id arrives from JSON and the console as text."""
    try:
        return int(str(target).strip()) in IMMUNE
    except (TypeError, ValueError):
        return False

KIND_BAN = "ban"
KIND_KICK = "kick"

# A loop that fires faster than this is indistinguishable from an attack on the
# guild and will burn the REST budget the rest of the bot needs.
MIN_INTERVAL = 5.0
MAX_INTERVAL = 6 * 3600.0
MAX_PASSES = 500


@dataclass
class Loop:
    """One armed loop."""

    id: str
    kind: str
    target: str
    reason: str
    interval: float
    passes: int
    armed_by: str
    notify: bool = False
    # 0 means "no DM was sent", so a failure to DM is never reported as a
    # successful delivery.
    dm_sent: bool = False
    started: float = field(default_factory=time.time)
    deadline: float = 0.0
    fired: int = 0
    last_error: str = ""
    stopped: str = ""
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "target": self.target,
            "reason": self.reason,
            "interval": self.interval,
            "passes": self.passes,
            "fired": self.fired,
            "armed_by": self.armed_by,
            "notify": self.notify,
            "dm_sent": self.dm_sent,
            "started": self.started,
            "deadline": self.deadline,
            "last_error": self.last_error,
            "stopped": self.stopped,
            "running": self.running,
        }

    @property
    def running(self) -> bool:
        return not self._stop.is_set() and self.fired < self.passes

    @property
    def remaining(self) -> int:
        return max(0, self.passes - self.fired)


class Loops:
    """Armed loops, keyed by id. One loop per target and kind at a time."""

    def __init__(self, rest, guild_id: int = GUILD_ID, clock=time.time) -> None:
        self.rest = rest
        self.guild_id = guild_id
        self._clock = clock
        self._loops: dict[str, Loop] = {}
        self._lock = threading.Lock()
        self._serial = 0

    # -- arming -----------------------------------------------------------
    def arm(self, kind: str, target: str, reason: str, interval: float,
            passes: int, armed_by: str, notify: bool = False) -> Loop:
        """Start a loop. Raises ValueError with a reason a human can act on."""
        kind = (kind or "").strip().lower()
        if kind not in (KIND_BAN, KIND_KICK):
            raise ValueError("kind must be ban or kick")
        target = str(target or "").strip()
        if not target.isdigit():
            raise ValueError("target must be a user id")
        if is_immune(target):
            raise ValueError("that member is protected and cannot be looped")

        interval = float(interval)
        if not MIN_INTERVAL <= interval <= MAX_INTERVAL:
            raise ValueError(
                f"interval must be between {int(MIN_INTERVAL)}s and "
                f"{int(MAX_INTERVAL)}s"
            )
        passes = int(passes)
        if not 1 <= passes <= MAX_PASSES:
            raise ValueError(f"passes must be between 1 and {MAX_PASSES}")

        with self._lock:
            for existing in self._loops.values():
                if (existing.target, existing.kind) == (target, kind) and existing.running:
                    raise ValueError(
                        f"a {kind} loop is already running on that member "
                        f"({existing.fired}/{existing.passes})"
                    )
            self._serial += 1
            loop_id = f"L{self._serial:03d}"
            loop = Loop(
                id=loop_id,
                kind=kind,
                target=target,
                reason=(reason or "no reason given")[:400],
                interval=interval,
                passes=passes,
                armed_by=str(armed_by),
                notify=bool(notify),
                deadline=self._clock() + interval * passes + 60,
            )
            self._loops[loop_id] = loop

        thread = threading.Thread(
            target=self._run, args=(loop,), name=f"loop-{loop_id}", daemon=True
        )
        thread.start()
        log.info("loop %s armed: %s %s every %ss x%s", loop_id, kind, target,
                 interval, passes)
        return loop

    def stop(self, loop_id: str, why: str = "stopped by operator") -> bool:
        with self._lock:
            loop = self._loops.get(loop_id)
        if loop is None:
            return False
        loop.stopped = why
        loop._stop.set()
        log.info("loop %s stopped: %s", loop_id, why)
        return True

    def stop_all(self, why: str = "all loops stopped") -> int:
        with self._lock:
            ids = list(self._loops)
        return sum(1 for i in ids if self.stop(i, why))

    # -- running ----------------------------------------------------------
    def _run(self, loop: Loop) -> None:
        """Fire until the pass count or the deadline is reached.

        The first pass fires immediately: an operator who arms a loop wants the
        member gone now, not one interval from now.
        """
        self._notify(loop)
        while loop.fired < loop.passes:
            if loop._stop.is_set():
                break
            if self._clock() > loop.deadline:
                loop.stopped = "deadline reached"
                break
            if is_immune(loop.target):
                loop.stopped = "target is protected"
                break

            try:
                status = self._fire(loop)
                loop.fired += 1
                if status not in (200, 204):
                    loop.last_error = f"HTTP {status}"
            except Exception as exc:  # a loop thread must never die silently
                loop.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("loop %s pass failed: %s", loop.id, loop.last_error)

            if loop.fired >= loop.passes:
                loop.stopped = "finished"
                break
            # Wait on the stop event, so a stop takes effect at once rather
            # than after a full interval.
            if loop._stop.wait(loop.interval):
                break

        if not loop.stopped:
            loop.stopped = "stopped" if loop._stop.is_set() else "finished"
        log.info("loop %s ended after %s passes (%s)", loop.id, loop.fired, loop.stopped)

    def _notify(self, loop: Loop) -> bool:
        """DM the member once, before the first pass. Never raises.

        Sent before the ban so the DM can actually be delivered: a banned user
        shares no guild with the bot and `open_dm` fails.
        """
        if not loop.notify or loop.dm_sent:
            return False
        try:
            verb = "banned" if loop.kind == KIND_BAN else "kicked"
            text = (
                f"You are being **{verb}** from Eternal repeatedly.\n"
                f"Reason: {loop.reason}"
            )
            loop.dm_sent = bool(self.rest.dm(int(loop.target), text))
        except Exception as exc:
            log.warning("loop %s DM failed: %s", loop.id, exc)
            loop.dm_sent = False
        return loop.dm_sent

    def _fire(self, loop: Loop) -> int:
        if loop.kind == KIND_BAN:
            # delete_seconds=0: a loop that also deletes a day of messages on
            # every pass would erase the channel it is meant to clean.
            return self.rest.ban(self.guild_id, int(loop.target), loop.reason, 0)
        return self.rest.kick(self.guild_id, int(loop.target), loop.reason)

    # -- reporting --------------------------------------------------------
    def listing(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = sorted(self._loops.values(), key=lambda l: l.started)
        return [r.to_json() for r in rows]

    def get(self, loop_id: str) -> Loop | None:
        return self._loops.get(loop_id)

    def active(self) -> list[Loop]:
        return [l for l in self._loops.values() if l.running]
