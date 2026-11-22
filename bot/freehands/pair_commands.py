"""Console pairing commands.

`+pair` is how a phone gets access without anyone typing a URL or a token.
The app shows a code, an operator runs `+pair <code>` here, and the phone
receives a token of its own. Approval has to happen inside Discord because
that is the only place the bot already knows who the operators are.
"""

from __future__ import annotations

import time

from .config import ALLOWED_OPS, GUILD_ID, LYNX_ID
from .log import log
from .pairing import Identity, normalise
from .people import _name_of, avatar_url
from .rest import RestError


def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


def _identity_for(engine, user_id: int, roles: set[int]) -> Identity:
    """Build a verified Identity from the guild, not from anything the app sent.

    The member endpoint is the source of truth: if the account is not in the
    guild the bot cannot vouch for it, and the claim is refused rather than
    trusted on the strength of a Discord id alone.
    """
    member = None
    try:
        member = engine.rest.member(GUILD_ID, int(user_id))
    except RestError as exc:
        log.warning("member lookup failed for %s: %s", user_id, exc)
    if not member:
        raise LookupError("that account is not a member of this server")
    username, display, avatar_hash = _name_of(member)
    member_roles = {int(r) for r in (member.get("roles") or [])} | set(roles)
    return Identity(
        user_id=str(user_id),
        username=username,
        display_name=display,
        avatar=avatar_url(str(user_id), avatar_hash),
        tier=engine.tier_of(user_id, member_roles),
    )


def pair(engine, command, user_id, message_id, channel_id, roles):
    """`+pair <code>` approves a console that is showing a code.

    The app opens the code and displays it; whoever runs this command in
    Discord is the account the console is bound to. Approval has to happen
    here because this is the only place the bot already knows who is typing -
    the app cannot vouch for its own identity.
    """
    if user_id not in ALLOWED_OPS:
        engine.reply(channel_id, message_id,
                     "Only an operator can pair a console.")
        return

    if not command.args:
        # No code given: explain the flow rather than minting one. A code
        # issued here could be photographed off the screen and used by anyone,
        # so the only safe direction is app -> Discord.
        engine.reply(
            channel_id, message_id,
            "Open the Freehands app and press **Connect to Discord**. It shows "
            "a code. Run `+pair <code>` with that code to approve this console "
            "as your account.",
        )
        return

    code = normalise(command.args[0])
    try:
        identity = _identity_for(engine, user_id, roles)
    except LookupError as exc:
        engine.reply(channel_id, message_id, f"Cannot pair: {exc}.")
        return

    # Say what is being approved. A code with no device name is exactly the
    # thing an operator should be suspicious of, so show the details first.
    pending = engine.pairing.peek(code)
    if pending is not None:
        engine.reply(
            channel_id, message_id,
            f"Approving **{pending['name']}**"
            + (f" ({pending['model']})" if pending["model"] else "")
            + f", code opened {_age(pending['age'])} ago"
            + (f" from {pending['ip']}" if pending["ip"] else "")
            + ".",
        )

    token = engine.pairing.approve(code, identity)
    if token is None:
        engine.reply(
            channel_id, message_id,
            f"No code `{code}` waiting. Codes last five minutes and can only "
            f"be used once — press Connect to Discord in the app for a fresh one.",
        )
        return

    device = engine.pairing.devices[max(
        engine.pairing.devices, key=lambda d: engine.pairing.devices[d].created)]
    engine.reply(
        channel_id, message_id,
        f"Paired **{device.name}** (`{device.id}`) as **{identity.label}** "
        f"({identity.tier}).\n"
        f"The app now has access; no token needs copying. "
        f"`+revoke {device.id}` disconnects it.",
    )
    log.info("device %s paired as %s (%s)", device.id, identity.label, identity.user_id)


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
