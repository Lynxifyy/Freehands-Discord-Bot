"""Console pairing commands.

`+pair` is how a phone gets access without anyone typing a URL or a token.
The app shows a code, an operator runs `+pair <code>` here, and the phone
receives a token of its own. Approval has to happen inside Discord because
that is the only place the bot already knows who the operators are.
"""

from __future__ import annotations

import time

from .config import ALLOWED_OPS, LYNX_ID
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
        code = engine.pairing.open("console", opened_by=str(user_id))
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


def _stamp(seconds: float) -> str:
    """Absolute time as well as an age: "14:32, 2h ago".

    An age alone is useless for "was that before or after I changed my
    password", which is exactly the question this command answers.
    """
    if not seconds:
        return "never"
    when = time.strftime("%d %b %H:%M", time.gmtime(seconds))
    return f"{when} ({_age(time.time() - seconds)} ago)"


def _where(d) -> str:
    ip = d.last_ip or d.ip or ""
    place = d.location
    if ip and place:
        return f"{place}  `{ip}`"
    if ip:
        return f"`{ip}`"
    return place or "unknown"


def devices(engine, command, user_id, message_id, channel_id, roles):
    """Who can control this bot, from where, and since when.

    Lynx-only: this is the full access list, including the address each phone
    paired from, and it should not be readable by every co-owner. The gate is
    in the command spec too; this check keeps the handler safe on its own.
    """
    if user_id != LYNX_ID:
        engine.reply(channel_id, message_id, "Only Lynx can see the device list.")
        return

    rows = sorted(engine.pairing.devices.values(), key=lambda d: d.created)
    if not rows:
        engine.reply(channel_id, message_id,
                     "No consoles paired. Run `+pair` to issue a code.")
        return

    lines = [f"**Paired consoles** — {len(rows)}", ""]
    for i, d in enumerate(rows, 1):
        sticker = "  \U0001F3F7 Freehands" if d.sticker == "freehands" else ""
        lines.append(f"**{i}. {d.name}**  `{d.id}`{sticker}")
        if d.owner_label:
            # A team console never has an address to show: it was never stored.
            lines.append(f"  {d.owner_label}")
        else:
            lines.append(f"  location: {_where(d)}")
        lines.append(f"  paired: {_stamp(d.created)}")
        lines.append(f"  last seen: {_stamp(d.last_seen)}")
        if d.paired_by:
            lines.append(f"  paired by: <@{d.paired_by}>")
        if d.app_version:
            lines.append(f"  app: {d.app_version}")
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
