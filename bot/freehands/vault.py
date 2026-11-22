"""Credential storage.

The token is a secret, so it is not in the tree at all. It is read from, in
order: the environment, `bot/.token`, or one of the legacy paths. `bot/.token`
is gitignored, which is the only thing that actually keeps a credential out of
a public repository - an obfuscated blob is still a published credential,
because anyone who can read the file can run the decoder next to it.

`unmask` survives for one reason: repositories created before this change have
a masked blob committed, and a fresh checkout of one needs a way to recover the
token into `bot/.token` once. Run `python -m freehands.vault --migrate` to do
that, then rotate the token and remove the blob from history.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
from pathlib import Path

SALT = b"freehands/v2/wake-sequence"

# The pre-2025 embedded blob. Kept so an old checkout can still boot and be
# migrated; empty in repositories created after the secret was moved out.
FRAGMENTS: tuple[str, ...] = ()


class MissingToken(RuntimeError):
    """No credential could be resolved."""


def _key(salt: bytes) -> bytes:
    return hashlib.sha256(salt).digest()


def unmask(fragments=FRAGMENTS, salt: bytes = SALT) -> str:
    """Decode a legacy fragment set back into the plaintext credential."""
    if not fragments:
        raise MissingToken("no embedded token; use bot/.token or FH_TOKEN")
    blob = base64.b64decode("".join(fragments))
    key = _key(salt)
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(blob)).decode()


def mask(token: str, salt: bytes = SALT, width: int = 24) -> list[str]:
    """Inverse of `unmask`; only used to migrate an existing blob."""
    key = _key(salt)
    blob = bytes(b ^ key[i % len(key)] for i, b in enumerate(token.encode()))
    enc = base64.b64encode(blob).decode()
    return [enc[i:i + width] for i in range(0, len(enc), width)]


def token_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".token"


def _candidates() -> list[Path]:
    pkg = Path(__file__).resolve().parent
    return [
        token_path(),
        pkg.parent / "token",
        pkg.parent.parent / ".openhands" / "bot" / "token",
        Path.home() / ".openhands" / "freehands_token",
    ]


def load_token() -> str:
    """Resolve the bot token: env, then a gitignored token file."""
    env = os.environ.get("FH_TOKEN") or os.environ.get("FREEHANDS_TOKEN")
    if env and env.strip():
        return env.strip()
    for path in _candidates():
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    raise MissingToken(
        "No bot token. Put it in bot/.token (gitignored) or set FH_TOKEN."
    )


def migrate() -> int:
    """Write the legacy embedded token into `bot/.token`, then report."""
    try:
        token = unmask()
    except MissingToken as exc:
        print(exc)
        return 1
    path = token_path()
    path.write_text(token + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"wrote {path} ({len(token)} chars). Now rotate the token in the "
          f"Discord developer portal and replace the file's contents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(migrate() if "--migrate" in sys.argv else 0)
