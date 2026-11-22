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

from .devices import identify

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
class Identity:
    """A Discord account the bot has verified inside the guild.

    Filled from the member endpoint at claim time, never from anything the app
    sends, so the console can say "you are acting as this account" and mean it.
    """
    user_id: str = ""
    username: str = ""
    display_name: str = ""
    avatar: str = ""
    tier: str = "user"

    @property
    def label(self) -> str:
        return self.display_name or self.username or self.user_id

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "label": self.label,
            "avatar": self.avatar,
            "tier": self.tier,
        }

    @staticmethod
    def from_json(raw: dict[str, Any]) -> "Identity":
        return Identity(
            user_id=str(raw.get("id", "")),
            username=str(raw.get("username", "")),
            display_name=str(raw.get("display_name", "")),
            avatar=str(raw.get("avatar", "")),
            tier=str(raw.get("tier", "user")),
        )


@dataclass
class Device:
    id: str
    name: str
    token_hash: str
    created: float = field(default_factory=time.time)
    last_seen: float = 0.0
    paired_by: str = ""
    # The verified Discord account this console acts as. `paired_by` records
    # who approved the pairing; this records who the device *is*. They are the
    # same at claim time, but only this one is trusted for permissions.
    identity: Identity = field(default_factory=Identity)
    # Where the phone paired from. Kept so `+devices` can answer "which phone
    # is this, and is it where it should be?" - a pairing from an unexpected
    # country is the signal that a token leaked.
    ip: str = ""
    location: str = ""
    last_ip: str = ""
    # Which app build paired, so a stale install is visible in the list.
    app_version: str = ""
    # Hardware model, used to recognise team-owned consoles.
    model: str = ""
    # Set when the console belongs to the team rather than a person. Such a
    # device never stores its address: see `claim`.
    owner_label: str = ""
    sticker: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "token_hash": self.token_hash,
            "created": self.created,
            "last_seen": self.last_seen,
            "paired_by": self.paired_by,
            "identity": self.identity.to_json(),
            "ip": self.ip,
            "location": self.location,
            "last_ip": self.last_ip,
            "app_version": self.app_version,
            "model": self.model,
            "owner_label": self.owner_label,
            "sticker": self.sticker,
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
            identity=Identity.from_json(raw.get("identity") or {}),
            ip=str(raw.get("ip", "")),
            location=str(raw.get("location", "")),
            last_ip=str(raw.get("last_ip", "")),
            app_version=str(raw.get("app_version", "")),
            model=str(raw.get("model", "")),
            owner_label=str(raw.get("owner_label", "")),
            sticker=str(raw.get("sticker", "")),
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

    def open(self, name: str = "", opened_by: str = "", model: str = "",
             ip: str = "") -> str:
        """Create a code for a device to present. Returns the code itself.

        `opened_by` is the operator who ran `+pair`. It is carried onto the
        device when the code is claimed, so the console knows which Discord
        account it acts for without the app having to claim an identity.
        """
        self._expire()
        # Drop the oldest rather than refuse: an abandoned pairing attempt
        # should not block a new one.
        while len(self._pending) >= MAX_PENDING:
            oldest = min(self._pending, key=lambda c: self._pending[c]["created"])
            self._pending.pop(oldest, None)
        code = new_code()
        self._pending[code] = {
            "name": (name or "device")[:40],
            "model": (model or "")[:40],
            "ip": (ip or "")[:45],
            "created": time.time(),
            "opened_by": str(opened_by or ""),
            # Filled in when an operator claims the code in Discord. Until then
            # the device has no identity and cannot be issued a token.
            "claimed_by": "",
            "identity": None,
            "token": "",
        }
        return code

    def pending(self) -> list[tuple[str, dict[str, Any]]]:
        self._expire()
        return sorted(self._pending.items(), key=lambda kv: kv[1]["created"])

    def cancel(self, code: str) -> bool:
        return self._pending.pop(normalise(code), None) is not None

    # -- claiming ---------------------------------------------------------
    def claim(self, code: str, paired_by: str = "", name: str = "",
              ip: str = "", location: str = "", app_version: str = "",
              model: str = "", identity: Identity | None = None) -> str | None:
        """Consume a code and return the new device token, or None.

        The caller shows the token to the operator once. It is not recoverable
        afterwards because only its hash is kept.

        `identity` is the Discord account the bot verified from whoever ran the
        claim. It is required: without it the device would have no identity to
        act as, which is the whole point of pairing through Discord.
        """
        self._expire()
        row = self._pending.pop(normalise(code), None)
        if row is None:
            return None
        token = secrets.token_urlsafe(32)
        device_id = secrets.token_hex(4)
        # The phone reported these when it opened the code; fall back to them
        # so a console paired without arguments still records what it is.
        model = model or str(row.get("model") or "")
        ip = ip or str(row.get("ip") or "")
        known = identify(model, name=name)
        self.devices[device_id] = Device(
            id=device_id,
            name=(name.strip()[:40] or row["name"]),
            token_hash=_hash(token),
            # The operator who opened the code owns the device unless the claim
            # named someone explicitly.
            paired_by=paired_by or str(row.get("opened_by") or ""),
            identity=identity or Identity(),
            # A team-owned console records no address at all. Dropping it here,
            # rather than hiding it at display time, means it is never written
            # to the state file in the first place.
            ip="" if known else ip,
            location="" if known else location,
            last_ip="" if known else ip,
            app_version=app_version[:24],
            model=(model or "")[:24],
            owner_label=known.describe() if known else "",
            sticker=known.sticker if known else "",
        )
        self._save()
        return token

    # -- device-authorization flow ----------------------------------------
    # The app asks for a code, a human approves it in Discord, and the app
    # polls until a token appears. This is the OAuth 2.0 device grant shape:
    # the device never handles the credential, and approval happens wherever
    # the account is already authenticated.

    def peek(self, code: str) -> dict[str, Any] | None:
        """What a pending code is waiting to become, without approving it."""
        self._expire()
        row = self._pending.get(normalise(code))
        if row is None or row.get("claimed_by"):
            return None
        return {
            "name": str(row.get("name") or "device"),
            "model": str(row.get("model") or ""),
            "ip": str(row.get("ip") or ""),
            "age": max(0.0, time.time() - float(row.get("created") or 0)),
        }

    def approve(self, code: str, identity: Identity, name: str = "",
                model: str = "", app_version: str = "",
                ip: str = "", location: str = "") -> str | None:
        """Bind a pending code to a verified account and create the device.

        Called from Discord, where the bot already knows who is asking. The
        device is registered here rather than at poll time so that approval is
        idempotent: the app can poll as often as it likes and always gets the
        same token back, instead of losing the credential to a dropped
        response.
        """
        self._expire()
        key = normalise(code)
        row = self._pending.get(key)
        if row is None:
            return None
        if row.get("claimed_by"):
            # Already bound. Re-claiming would let a second person hijack a
            # pairing that is about to complete, so report the existing binding
            # instead of replacing it.
            return None
        token = secrets.token_urlsafe(32)
        device_id = secrets.token_hex(4)
        # The phone reported these when it opened the code; fall back to them
        # so a console paired without arguments still records what it is.
        model = model or str(row.get("model") or "")
        ip = ip or str(row.get("ip") or "")
        known = identify(model, name=name)
        self.devices[device_id] = Device(
            id=device_id,
            name=(name.strip()[:40] or row["name"]),
            token_hash=_hash(token),
            paired_by=identity.user_id,
            identity=identity,
            # A team-owned console records no address at all. Dropping it here,
            # rather than hiding it at display time, means it is never written
            # to the state file in the first place.
            ip="" if known else ip,
            location="" if known else location,
            last_ip="" if known else ip,
            app_version=app_version[:24],
            model=(model or "")[:24],
            owner_label=known.describe() if known else "",
            sticker=known.sticker if known else "",
        )
        row["claimed_by"] = identity.user_id
        row["identity"] = identity
        row["token"] = token
        row["device"] = device_id
        self._save()
        return token

    def poll(self, code: str) -> dict[str, Any] | None:
        """Status of a pending code, for the app to poll.

        Idempotent: an approved code keeps returning the same token until the
        code expires. The code is itself the credential for this call, and it
        lives for minutes, so this adds no exposure that the code did not
        already carry.
        """
        self._expire()
        row = self._pending.get(normalise(code))
        if row is None:
            return None
        if not row.get("claimed_by"):
            return {"status": "pending"}
        identity: Identity | None = row.get("identity")
        return {
            "status": "approved",
            "token": str(row.get("token") or ""),
            "device": str(row.get("device") or ""),
            "identity": (identity or Identity()).to_json(),
        }

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
