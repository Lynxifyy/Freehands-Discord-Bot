"""Device pairing: how a phone gets a credential without anyone typing one.

A control API token is not something a person should have to copy from a
terminal into a phone keyboard. Instead the app asks the bot for a short code,
an operator approves it inside Discord, and the phone receives a token of its
own. Nothing secret is ever displayed for a human to transcribe.

The token is shown once, at claim time, and only its SHA-256 is stored. A
state file that leaks therefore does not leak a working credential, and a
token can be revoked per device instead of rotating one shared secret for
everyone.

Codes are six characters from an alphabet without lookalikes (no 0/O, 1/I/L),
because they get read off a screen and typed on a phone. They expire quickly
and are consumed on use, so a code seen over a shoulder is worthless later.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

# No 0/O, 1/I/L: those are the pairs people mistype when copying from a screen.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6
CODE_TTL = 300.0        # seconds a pending code stays claimable
MAX_PENDING = 5         # codes outstanding at once, so the list stays readable


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalise(code: str) -> str:
    """Accept what a person actually types: lowercase, spaces, stray dashes."""
    return "".join(c for c in code.upper() if c.isalnum())


@dataclass
class Device:
    id: str
    name: str
    token_hash: str
    created: float = field(default_factory=time.time)
    last_seen: float = 0.0
    paired_by: str = ""
    # Where the phone paired from. Kept so `+devices` can answer "which phone
    # is this, and is it where it should be?" - a pairing from an unexpected
    # country is the signal that a token leaked.
    ip: str = ""
    location: str = ""
    last_ip: str = ""
    # Which app build paired, so a stale install is visible in the list.
    app_version: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "token_hash": self.token_hash,
            "created": self.created,
            "last_seen": self.last_seen,
            "paired_by": self.paired_by,
            "ip": self.ip,
            "location": self.location,
            "last_ip": self.last_ip,
            "app_version": self.app_version,
        }

    @staticmethod
    def from_json(raw: dict[str, Any]) -> "Device":
        return Device(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "device")),
            token_hash=str(raw.get("token_hash", "")),
            created=float(raw.get("created", 0.0)),
            last_seen=float(raw.get("last_seen", 0.0)),
            paired_by=str(raw.get("paired_by", "")),
            ip=str(raw.get("ip", "")),
            location=str(raw.get("location", "")),
            last_ip=str(raw.get("last_ip", "")),
            app_version=str(raw.get("app_version", "")),
        )


class Pairing:
    """Pending codes and paired devices.

    Held in memory for pending codes: they are worthless in seconds, and a
    restart should cancel a pairing in progress rather than resurrect a code
    nobody is watching. Devices persist, because losing them would log every
    phone out.
    """

    def __init__(self, store=None) -> None:
        self.store = store
        self._pending: dict[str, dict[str, Any]] = {}
        self.devices: dict[str, Device] = {}
        if store is not None:
            for raw in getattr(store, "devices", []) or []:
                d = Device.from_json(raw)
                if d.id and d.token_hash:
                    self.devices[d.id] = d

    # -- pending codes ----------------------------------------------------
    def _expire(self) -> None:
        now = time.time()
        for code in [c for c, row in self._pending.items() if now - row["created"] > CODE_TTL]:
            self._pending.pop(code, None)

    def open(self, name: str = "") -> str:
        """Create a code for a device to present. Returns the code itself."""
        self._expire()
        # Drop the oldest rather than refuse: an abandoned pairing attempt
        # should not block a new one.
        while len(self._pending) >= MAX_PENDING:
            oldest = min(self._pending, key=lambda c: self._pending[c]["created"])
            self._pending.pop(oldest, None)
        code = new_code()
        self._pending[code] = {"name": (name or "device")[:40], "created": time.time()}
        return code

    def pending(self) -> list[tuple[str, dict[str, Any]]]:
        self._expire()
        return sorted(self._pending.items(), key=lambda kv: kv[1]["created"])

    def cancel(self, code: str) -> bool:
        return self._pending.pop(normalise(code), None) is not None

    # -- claiming ---------------------------------------------------------
    def claim(self, code: str, paired_by: str = "", name: str = "",
              ip: str = "", location: str = "", app_version: str = "") -> str | None:
        """Consume a code and return the new device token, or None.

        The caller shows the token to the operator once. It is not recoverable
        afterwards because only its hash is kept.
        """
        self._expire()
        row = self._pending.pop(normalise(code), None)
        if row is None:
            return None
        token = secrets.token_urlsafe(32)
        device_id = secrets.token_hex(4)
        self.devices[device_id] = Device(
            id=device_id,
            name=(name.strip()[:40] or row["name"]),
            token_hash=_hash(token),
            paired_by=paired_by,
            ip=ip,
            location=location,
            last_ip=ip,
            app_version=app_version[:24],
        )
        self._save()
        return token

    # -- auth -------------------------------------------------------------
    def verify(self, token: str) -> Device | None:
        """Constant-time lookup by token. Returns the device when it matches."""
        if not token:
            return None
        digest = _hash(token)
        match = None
        for device in self.devices.values():
            # Compare every device so timing does not reveal a near match.
            if hmac.compare_digest(device.token_hash, digest):
                match = device
        if match is not None:
            match.last_seen = time.time()
        return match

    def touch(self, device: "Device", ip: str = "") -> None:
        """Record that a device was seen, without rewriting the whole store.

        `last_seen` is already set by `verify`; the address is only worth
        persisting when it changed, so a chatty poll does not rewrite state.
        """
        if ip and ip != device.last_ip:
            device.last_ip = ip
            self._save()

    def revoke(self, device_id: str) -> bool:
        if self.devices.pop(device_id, None) is None:
            return False
        self._save()
        return True

    def revoke_all(self) -> int:
        count = len(self.devices)
        self.devices.clear()
        self._save()
        return count

    def _save(self) -> None:
        if self.store is None:
            return
        self.store.devices = [d.to_json() for d in self.devices.values()]
        self.store.touch()
        self.store.save(force=True)
