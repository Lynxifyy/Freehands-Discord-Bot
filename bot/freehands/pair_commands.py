"""Console pairing commands.

`+pair` is how a phone gets access without anyone typing a URL or a token.
The app shows a code, an operator runs `+pair <code>` here, and the phone
receives a token of its own. Approval has to happen inside Discord because
that is the only place the bot already knows who the operators are.
"""

from __future__ import annotations

import time

from .config import ALLOWED_OPS
from .log import log


def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


def pair(engine, command, user_id, message_id, channel_id, roles):
    """`+pair` opens a code, `+pair <code>` claims one for the asking device."""
    if user_id not in ALLOWED_OPS:
        engine.reply(channel_id, message_id,
                     "Only an operator can pair a console.")
        return

    if not command.args:
        code = engine.pairing.open("console")
        engine.reply(
            channel_id, message_id,
            f"Pairing code `{code}` — valid for 5 minutes.\n"
            f"Enter it in the app. Running `+pair` again issues a new code and "
            f"cancels this one.",
        )
        log.info("pairing code opened by %s", user_id)
        return

    code = command.args[0]
    token = engine.pairing.claim(code, paired_by=str(user_id))
    if token is None:
        engine.reply(channel_id, message_id,
                     f"No code `{code.upper()}` waiting. It may have expired — "
                     f"run `+pair` in the app for a fresh one.")
        return

    device = max(engine.pairing.devices.values(), key=lambda d: d.created)
    # The token is shown once. Only its hash is stored, so it cannot be
    # recovered later; losing it means revoking and pairing again.
    engine.reply(
        channel_id, message_id,
        f"Paired **{device.name}** (`{device.id}`).\n"
        f"Token, shown once: `{token}`\n"
        f"`+revoke {device.id}` disconnects it.",
    )
    log.info("device %s paired by %s", device.id, user_id)


def devices(engine, command, user_id, message_id, channel_id, roles):
    rows = sorted(engine.pairing.devices.values(), key=lambda d: d.created)
    if not rows:
        engine.reply(channel_id, message_id,
                     "No consoles paired. Run `+pair` to issue a code.")
        return
    lines = [f"**Paired consoles** ({len(rows)})", ""]
    now = time.time()
    for d in rows:
        seen = f"{_age(now - d.last_seen)} ago" if d.last_seen else "never used"
        lines.append(f"`{d.id}` **{d.name}** — paired {_age(now - d.created)} ago, last seen {seen}")
    lines.append("")
    lines.append("`+revoke <id>` disconnects one. `+revoke all` disconnects every device.")
    engine.reply(channel_id, message_id, "\n".join(lines))


def revoke(engine, command, user_id, message_id, channel_id, roles):
    if not command.args:
        engine.reply(channel_id, message_id, "Use `+revoke <id>` or `+revoke all`.")
        return
    target = command.args[0].lower()
    if target == "all":
        count = engine.pairing.revoke_all()
        engine.reply(channel_id, message_id,
                     f"Revoked {count} device{'s' if count != 1 else ''}."
                     if count else "No devices to revoke.")
        return
    if engine.pairing.revoke(target):
        engine.reply(channel_id, message_id, f"Revoked `{target}`.")
    else:
        engine.reply(channel_id, message_id, f"No device `{target}`.")
