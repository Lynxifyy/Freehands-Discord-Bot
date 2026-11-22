"""Command implementations.

Each handler takes `(engine, command, user_id, message_id, channel_id, roles)`.
Keeping them out of `engine.py` stops that module growing into a monolith and
makes the permission table in `register()` the single place to audit.
"""

from __future__ import annotations

import time
from dataclasses import replace

from . import text
from .commands import Spec, user_id_from
from .tempown import DEFAULT_MINUTES
from .config import (
    ARCEUS_ID,
    BOT_ID,
    GUILD_ID,
    LYNX_ID,
    OWNER_ID,
    MAIN_CHAT_ID,
    ROLE_CO_OWNER,
    ROLE_ETERNAL,
    WATCH_ID,
)
from .engine import TIER_ORDER
from .log import stats


def _bind(engine, handler):
    """Turn `handler(engine, cmd, uid, mid, cid, roles)` into a dispatch target."""
    def bound(command, user_id, message_id, channel_id, roles):
        return handler(engine, command, user_id, message_id, channel_id, roles)

    bound.__name__ = handler.__name__
    return bound


def register(engine) -> None:
    add = engine.registry.add
    add(Spec("help", _bind(engine, help_), "user", "+help", "list commands"))
    add(Spec("ping", _bind(engine, ping), "user", "+ping", "latency check"))
    add(Spec("stats", _bind(engine, stats_), "user", "+stats", "counters and uptime"))
    add(Spec("codes", _bind(engine, codes), "user", "+codes", "list the codebook"))
    add(Spec("incidents", _bind(engine, incidents), "mod", "+incidents [n]", "recent code hits"))
    add(Spec("question", _bind(engine, question), "user", "+question <text>", "ask the operators"))

    add(Spec("antiban", _bind(engine, antiban), "owner", "+antiban on|off", "ban protection"))
    add(Spec("keepbanned", _bind(engine, keepbanned), "owner",
             "+keepbanned add|remove <user>", "anti-ban exceptions", aliases=("kb",)))
    add(Spec("mod", _bind(engine, mod), "owner", "+mod on|off", "moderation switch"))
    add(Spec("automod", _bind(engine, automod), "owner", "+automod on|off", "auto-mod switch"))
    add(Spec("codesense", _bind(engine, codesense), "owner", "+codesense on|off", "code sensing switch"))
    add(Spec("watch", _bind(engine, watch), "owner", "+watch on|off", "watch the flagged member"))
    add(Spec("ops", _bind(engine, ops), "owner", "+ops create|lock|status",
             "the private operator channel", aliases=("opchan",)))
    add(Spec("watchtarget", _bind(engine, dyllan), "owner", "+watchtarget on|off|status",
             "arm or disarm the flagged-member watch",
             aliases=("dyllan", "ms")))
    add(Spec("lock", _bind(engine, lock), "owner", "+lock", "lock the channel"))
    add(Spec("unlock", _bind(engine, unlock), "owner", "+unlock", "unlock the channel"))
    add(Spec("lockvote", _bind(engine, lockvote), "owner", "+lockvote yes|no", "vote on a lockdown"))
    add(Spec("approve", _bind(engine, approve), "owner", "+approve", "approve a pending ban"))
    add(Spec("deny", _bind(engine, deny), "owner", "+deny", "deny a pending ban"))

    add(Spec("ban", _bind(engine, ban), "owner", "+ban <user> [reason]", "ban (refused while anti-ban)"))
    add(Spec("unban", _bind(engine, unban), "owner", "+unban <user>", "unban"))
    add(Spec("kick", _bind(engine, kick), "owner", "+kick <user>", "kick"))
    add(Spec("glaze", _bind(engine, glaze), "owner", "+glaze on|off",
             "flattering replies when Lynx is mentioned"))
    add(Spec("loopban", _bind(engine, loopban), "owner",
             "+loopban <user> <passes> [interval] [reason]",
             "repeat a ban on a timer", aliases=("lban",)))
    add(Spec("loopkick", _bind(engine, loopkick), "owner",
             "+loopkick <user> <passes> [interval] [reason]",
             "repeat a kick on a timer", aliases=("lkick",)))
    add(Spec("loopstop", _bind(engine, loopstop), "owner", "+loopstop <id>|all",
             "stop one loop or every loop"))
    add(Spec("loops", _bind(engine, loops_), "mod", "+loops", "list armed loops"))
    add(Spec("mute", _bind(engine, mute), "mod", "+mute <user> [10m] [reason]", "timeout"))
    add(Spec("unmute", _bind(engine, unmute), "mod", "+unmute <user>", "clear timeout"))
    add(Spec("nomute", _bind(engine, nomute), "owner", "+nomute on|off", "freeze all mutes"))
    add(Spec("takeall", _bind(engine, takeall), "owner", "+takeall <user>", "strip every role"))
    add(Spec("demote", _bind(engine, demote), "owner", "+demote <user> <reason>",
             "strip all roles, tell them why, notify the owner"))
    add(Spec("bankrupt", _bind(engine, bankrupt), "user", "+bankrupt <user>",
             "strip every role and notify them",
             aliases=("bankruptrecover",)))
    add(Spec("recover", _bind(engine, recover), "owner", "+recover", "grant co-owner"))
    add(Spec("snapshot", _bind(engine, snapshot), "owner", "+snapshot <user>", "save roles"))
    add(Spec("restore", _bind(engine, restore), "owner", "+restore <user>", "restore saved roles"))
    add(Spec("strikes", _bind(engine, strikes), "mod", "+strikes <user>", "show strikes"))
    add(Spec("clearstrikes", _bind(engine, clearstrikes), "owner", "+clearstrikes <user>", "reset strikes"))
    add(Spec("purge", _bind(engine, purge), "mod", "+purge [n]", "delete recent messages"))
    add(Spec("say", _bind(engine, say), "owner", "+say <text>", "speak as the bot"))
    add(Spec("temp ownership", _bind(engine, tempownership), "owner",
             "+Temp Ownership @user [minutes]", "lend ownership for 10 minutes",
             aliases=("tempownership", "tempowner", "temp"), only_user=LYNX_ID))

    add(Spec("whois", _bind(engine, whois), "mod", "+whois <user>", "member summary"))

    from . import pair_commands
    add(Spec("pair", _bind(engine, pair_commands.pair), "owner", "+pair [code]",
             "pair the console app",
             detail="Run with no code to issue a pairing code for the app, then "
                    "run +pair <code> with the code the app shows. The app then "
                    "gets its own token, so nobody types a URL or a secret."))
    add(Spec("devices", _bind(engine, pair_commands.devices), "owner", "+devices",
             "list paired consoles",
             detail="Every phone that can control the bot, when it was paired and "
                    "when it was last used."))
    add(Spec("revoke", _bind(engine, pair_commands.revoke), "owner",
             "+revoke <id|all>", "disconnect a console",
             detail="Cut off one paired phone, or all of them. Use this if a "
                    "device is lost or a token leaks."))

    from . import test_command
    add(Spec("test", _bind(engine, test_command.run), "owner", "+test",
             "check the bot is working",
             detail="Runs live checks against Discord, the event log, the "
                    "pairing store and the command registry, then reports what "
                    "passed. Use it when something seems wrong."))


def _flag(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in ("on", "true", "yes", "1", "enable", "enabled"):
        return True
    if lowered in ("off", "false", "no", "0", "disable", "disabled"):
        return False
    return None


def _switch(engine, command, message_id, channel_id, name: str, current: bool,
            setter) -> None:
    if not command.args:
        engine.reply(channel_id, message_id, f"`{name}` is {'on' if current else 'off'}.")
        return
    value = _flag(command.args[0])
    if value is None:
        engine.reply(channel_id, message_id, f"Use `+{name} on` or `+{name} off`.")
        return
    setter(value)
    engine.store.touch()
    engine.store.save()
    engine.reply(channel_id, message_id, f"`{name}` is now {'on' if value else 'off'}.")


# -- informational -------------------------------------------------------
def help_(engine, command, user_id, message_id, channel_id, roles):
    tier = engine.tier_of(user_id, roles)
    lines = ["**Freehands commands**", ""]
    current = None
    for spec in engine.registry.by_tier(tier):
        if spec.tier != current:
            current = spec.tier
            lines.append(f"__{current}__")
        lines.append(f"`{spec.usage}` — {spec.summary}")
    lines += ["", "Prefix `+`. Codes need no prefix: `code 8`.", ""]
    lines.append("**Codes** " + ", ".join(
        f"{c.number}={c.title}" for c in engine.book.listing()
    ))
    engine.reply(channel_id, message_id, "\n".join(lines))


def ping(engine, command, user_id, message_id, channel_id, roles):
    started = time.time()
    engine.rest.typing(channel_id)
    engine.reply(channel_id, message_id, f"Pong — {(time.time() - started) * 1000:.0f} ms")


def stats_(engine, command, user_id, message_id, channel_id, roles):
    c = stats.counts
    s = engine.settings
    engine.reply(channel_id, message_id, "\n".join([
        f"**Uptime** {stats.uptime()}",
        f"**Messages** {c.get('messages', 0)} · **commands** {c.get('commands', 0)} "
        f"· **denied** {c.get('denied', 0)}",
        f"**Codes** {c.get('codes', 0)} · **slur strikes** {c.get('slur_strikes', 0)} "
        f"· **unbans** {c.get('unbans', 0)}",
        f"**anti-ban** {'on' if s.anti_ban else 'off'} · "
        f"**moderation** {'on' if s.moderation_enabled else 'off'} · "
        f"**automod** {'on' if s.automod else 'off'} · "
        f"**code sense** {'on' if s.codes_enabled else 'off'}",
        f"**keep-banned** {', '.join(f'<@{u}>' for u in sorted(s.keep_banned)) or 'nobody'}",
    ]))


def codes(engine, command, user_id, message_id, channel_id, roles):
    lines = ["**Codebook**", ""]
    for code in engine.book.listing():
        pings = [n for n, on in (("owner", code.ping_owner), ("arceus", code.ping_arceus)) if on]
        suffix = f" · pings {', '.join(pings)}" if pings else ""
        silence = " · deletes trigger" if code.silence else ""
        lines.append(f"`{code.number}` **{code.title}** ({code.severity}) — {code.meaning}{suffix}{silence}")
    lines += ["", "Say `code <n>` in chat to raise one."]
    engine.reply(channel_id, message_id, "\n".join(lines))


def incidents(engine, command, user_id, message_id, channel_id, roles):
    limit = 10
    if command.args and command.args[0].isdigit():
        limit = min(int(command.args[0]), 25)
    rows = engine.store.incidents[-limit:]
    if not rows:
        engine.reply(channel_id, message_id, "No code incidents recorded.")
        return
    lines = ["**Recent incidents**", ""]
    for row in rows:
        when = time.strftime("%d %b %H:%M", time.gmtime(row.get("at", 0)))
        lines.append(
            f"`{when}` code {row.get('code')} — {row.get('title')} "
            f"(<@{row.get('by')}>, \"{row.get('trigger', '')}\")"
        )
    engine.reply(channel_id, message_id, "\n".join(lines))


def question(engine, command, user_id, message_id, channel_id, roles):
    if not command.text:
        engine.reply(channel_id, message_id, "Ask something: `+question why is the channel locked?`")
        return
    engine.store.questions[f"q{message_id}"] = {
        "user": user_id, "text": command.text, "at": int(time.time()),
    }
    engine.store.save()
    engine.send(
        MAIN_CHAT_ID,
        f"**Question from** <@{user_id}>\n{command.text}\n\n"
        f"<@{LYNX_ID}> answer with `+answer {message_id} <text>`.",
    )
    engine.reply(channel_id, message_id, "Question posted.")


# -- switches ------------------------------------------------------------
def antiban(engine, command, user_id, message_id, channel_id, roles):
    def setter(value: bool) -> None:
        engine.settings.anti_ban = value
        engine.mod.settings = engine.settings
        if value:
            lifted = engine.mod.anti_ban_sweep()
            engine.reply(channel_id, message_id,
                         f"Anti-ban armed. Lifted {len(lifted)} ban(s).")
        else:
            engine.reply(channel_id, message_id, "Anti-ban disarmed. Bans will stand.")
    _switch(engine, command, message_id, channel_id, "antiban",
            engine.settings.anti_ban, setter)


def keepbanned(engine, command, user_id, message_id, channel_id, roles):
    kb = engine.settings.keep_banned
    if not command.args:
        engine.reply(channel_id, message_id,
                     "Keep-banned: " + (", ".join(f"<@{u}>" for u in sorted(kb)) or "nobody"))
        return
    action = command.args[0].lower()
    target = user_id_from(command.args[1]) if len(command.args) > 1 else None
    if action == "add" and target:
        kb.add(target)
        engine.mod.enforce_keep_banned()
        engine.reply(channel_id, message_id, f"<@{target}> is now keep-banned and re-banned.")
    elif action in ("remove", "del") and target:
        kb.discard(target)
        engine.reply(channel_id, message_id, f"<@{target}> is no longer keep-banned.")
    else:
        engine.reply(channel_id, message_id, "Use `+keepbanned add|remove <user>`.")
        return
    engine.store.touch()
    engine.store.save()


def mod(engine, command, user_id, message_id, channel_id, roles):
    _switch(engine, command, message_id, channel_id, "mod",
            engine.settings.moderation_enabled,
            lambda v: setattr(engine.settings, "moderation_enabled", v))


def automod(engine, command, user_id, message_id, channel_id, roles):
    _switch(engine, command, message_id, channel_id, "automod",
            engine.settings.automod,
            lambda v: setattr(engine.settings, "automod", v))


def codesense(engine, command, user_id, message_id, channel_id, roles):
    _switch(engine, command, message_id, channel_id, "codesense",
            engine.settings.codes_enabled,
            lambda v: setattr(engine.settings, "codes_enabled", v))


def watch(engine, command, user_id, message_id, channel_id, roles):
    def setter(value: bool) -> None:
        engine.settings.watch_enabled = value
        engine.reply(channel_id, message_id,
                     f"Watching <@{WATCH_ID}> is now {'on' if value else 'off'}.")
    _switch(engine, command, message_id, channel_id, "watch",
            engine.settings.watch_enabled, setter)


# -- private operator channel --------------------------------------------
def ops(engine, command, user_id, message_id, channel_id, roles):
    arg = (command.args[0].lower() if command.args else "status")
    if arg in ("create", "new", "recreate"):
        try:
            cid = engine.ensure_ops(force_new=arg in ("new", "recreate"))
        except Exception as exc:
            engine.reply(channel_id, message_id, f"Could not create it: `{exc}`")
            return
        engine.reply(channel_id, message_id,
                     f"Private channel ready: <#{cid}>. Only the owner, Arceus, "
                     f"Lynx and me can see it.")
        return
    if arg == "lock":
        engine.ops._lock()
        engine.reply(channel_id, message_id,
                     f"Locked down: only owner, Arceus and Lynx can see "
                     f"{engine.ops.describe()}.")
        return
    if arg == "audit":
        a = engine.ops.audit()
        lines = [f"**Ops channel audit** {engine.ops.describe()}", ""]
        lines.append(f"**Allowed** owner, Arceus, Lynx, me")
        if a.missing:
            lines.append(
                f"**Cannot view the channel** {', '.join(f'<@{u}>' for u in a.missing)}"
                " - run `+ops lock` to restore their overwrite"
            )
        else:
            lines.append("**All three operators can view it.**")
        lines.append("")
        lines.append(
            "**Note** Discord's Administrator permission ignores channel "
            "overwrites, so anyone holding a role with Administrator can still "
            "read this channel. Only the owner can fix that by removing "
            "Administrator from those roles."
        )
        engine.reply(channel_id, message_id, "\n".join(lines))
        return
    state = "armed" if engine.settings.watch_armed else "disarmed"
    engine.reply(
        channel_id, message_id,
        f"**Ops channel** {engine.ops.describe()}\n"
        f"**Allowed** owner, Arceus, Lynx, me\n"
        f"**Watch ({WATCH_ID})** {state}\n"
        f"\n`+ops create` | `+ops lock` | `+watchtarget on|off`",
    )


def dyllan(engine, command, user_id, message_id, channel_id, roles):
    """Arm or disarm the watch. Named `+watchtarget`; `+dyllan` still works."""
    arg = (command.args[0].lower() if command.args else "status")
    if arg in ("on", "arm", "start", "watch"):
        engine.arm_watch(True)
        engine.reply(channel_id, message_id,
                     f"Watch armed. Every message from <@{WATCH_ID}> now goes "
                     f"to {engine.ops.describe()} and is screened.")
        return
    if arg in ("off", "disarm", "stop"):
        engine.arm_watch(False)
        engine.reply(channel_id, message_id, f"Watch disarmed for <@{WATCH_ID}>.")
        return
    state = "armed" if engine.settings.watch_armed else "disarmed"
    engine.reply(channel_id, message_id,
                 f"<@{WATCH_ID}> watch is **{state}**. `+watchtarget on|off` to change it.")


# -- channel state -------------------------------------------------------
def lock(engine, command, user_id, message_id, channel_id, roles):
    ok = engine.mod.set_channel_locked(MAIN_CHAT_ID, True)
    engine.reply(channel_id, message_id, "Channel locked." if ok else "Lock failed.")


def unlock(engine, command, user_id, message_id, channel_id, roles):
    ok = engine.mod.set_channel_locked(MAIN_CHAT_ID, False)
    engine.reply(channel_id, message_id, "Channel unlocked." if ok else "Unlock failed.")


def lockvote(engine, command, user_id, message_id, channel_id, roles):
    vote = (command.args[0].lower() if command.args else "")
    if vote not in ("yes", "no"):
        engine.reply(channel_id, message_id, "Use `+lockvote yes` or `+lockvote no`.")
        return
    ballot = engine.store.questions.setdefault("lockvote", {"votes": []})
    voters = ballot.setdefault("votes", [])
    if user_id not in voters:
        voters.append(user_id)
    needed = 3
    if vote == "no":
        engine.store.questions.pop("lockvote", None)
        engine.reply(channel_id, message_id, "Lockdown cancelled.")
        return
    if len(voters) >= needed:
        engine.mod.set_channel_locked(MAIN_CHAT_ID, True)
        engine.store.questions.pop("lockvote", None)
        engine.reply(channel_id, message_id, f"Lockdown approved by {len(voters)} votes. Locked.")
    else:
        engine.reply(channel_id, message_id, f"Vote {len(voters)}/{needed} recorded.")
    engine.store.save()


# -- pending approvals ---------------------------------------------------
def approve(engine, command, user_id, message_id, channel_id, roles):
    pending = engine.store.questions.pop("slur", None)
    if not pending:
        engine.reply(channel_id, message_id, "Nothing pending.")
        return
    target = pending["user"]
    if engine.settings.anti_ban:
        engine.reply(channel_id, message_id,
                     f"Refused — anti-ban is armed, so <@{target}> cannot be banned. "
                     f"`+antiban off` first.")
        return
    status = engine.rest.ban(GUILD_ID, target, "approved by operator")
    engine.reply(channel_id, message_id,
                 f"<@{target}> banned ({status})." if status in (200, 204) else f"Ban failed ({status}).")
    engine.store.clear_strikes(target)
    engine.store.save()


def deny(engine, command, user_id, message_id, channel_id, roles):
    pending = engine.store.questions.pop("slur", None)
    if not pending:
        engine.reply(channel_id, message_id, "Nothing pending.")
        return
    engine.reply(channel_id, message_id, f"Ban for <@{pending['user']}> denied.")
    engine.store.save()


# -- moderation ----------------------------------------------------------
def ban(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+ban <user> [reason]`")
        return
    if engine.settings.anti_ban:
        engine.reply(channel_id, message_id, "Refused — anti-ban is armed.")
        return
    if target in engine.settings.keep_banned:
        engine.settings.keep_banned.discard(target)
    reason = " ".join(command.args[1:]) or "no reason given"
    status = engine.rest.ban(GUILD_ID, target, reason)
    engine.reply(channel_id, message_id,
                 f"<@{target}> banned." if status in (200, 204) else f"Ban failed ({status}).")


def unban(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+unban <user>`")
        return
    engine.settings.keep_banned.discard(target)
    engine.store.known_bans.discard(target)
    engine.store.save()
    status = engine.rest.unban(GUILD_ID, target, "manual unban")
    engine.reply(channel_id, message_id,
                 f"<@{target}> unbanned." if status in (200, 204) else f"Unban failed ({status}).")


def kick(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+kick <user>`")
        return
    status = engine.rest.kick(GUILD_ID, target, " ".join(command.args[1:]) or "kick")
    engine.reply(channel_id, message_id,
                 f"<@{target}> kicked." if status in (200, 204) else f"Kick failed ({status}).")



def glaze(engine, command, user_id, message_id, channel_id, roles):
    want = (command.args[0].lower() if command.args else "")
    if want not in ("on", "off"):
        engine.reply(channel_id, message_id,
                     f"Glaze is {'on' if engine.settings.glaze_enabled else 'off'}. "
                     f"Use `+glaze on|off`.")
        return
    engine.settings.glaze_enabled = want == "on"
    engine.store.touch()
    engine.reply(channel_id, message_id,
                 f"Glaze {'on' if engine.settings.glaze_enabled else 'off'}.")


def loopban(engine, command, user_id, message_id, channel_id, roles):
    return _loop(engine, command, user_id, message_id, channel_id, "ban")


def loopkick(engine, command, user_id, message_id, channel_id, roles):
    return _loop(engine, command, user_id, message_id, channel_id, "kick")


def _loop(engine, command, user_id, message_id, channel_id, kind):
    """`+loopban <user> <passes> [interval] [reason]`"""
    args = list(command.args)
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id,
                     f"Who? `+loop{kind} <user> <passes> [interval] [reason]`")
        return
    # Drop the target token, whatever form it was written in.
    while args and not args[0].lstrip("<@!>").isdigit():
        args.pop(0)
    if not args or not args[0].isdigit():
        engine.reply(channel_id, message_id,
                     f"How many passes? `+loop{kind} <user> <passes> [interval] [reason]`")
        return
    passes = int(args.pop(0))
    interval = 60.0
    if args and args[0].rstrip("s").replace(".", "", 1).isdigit():
        interval = float(args.pop(0).rstrip("s"))
    reason = " ".join(args) or "loop"
    try:
        loop = engine.loops.arm(kind, str(target), reason, interval, passes, str(user_id))
    except ValueError as exc:
        engine.reply(channel_id, message_id, f"Refused — {exc}.")
        return
    engine.reply(channel_id, message_id,
                 f"{loop.id}: {kind} loop on <@{target}> — {passes} passes every "
                 f"{int(interval)}s. `+loopstop {loop.id}` ends it.")


def loopstop(engine, command, user_id, message_id, channel_id, roles):
    target = (command.args[0] if command.args else "").upper()
    if target == "ALL":
        n = engine.loops.stop_all("stopped by operator")
        engine.reply(channel_id, message_id, f"Stopped {n} loop{'s' if n != 1 else ''}.")
        return
    if not target:
        engine.reply(channel_id, message_id, "Use `+loopstop <id>` or `+loopstop all`.")
        return
    ok = engine.loops.stop(target)
    engine.reply(channel_id, message_id,
                 f"Stopped {target}." if ok else f"No loop `{target}`.")


def loops_(engine, command, user_id, message_id, channel_id, roles):
    rows = engine.loops.listing()
    if not rows:
        engine.reply(channel_id, message_id, "No loops armed.")
        return
    lines = [f"**Loops** — {len(rows)}", ""]
    for r in rows:
        state = "running" if r["running"] else r["stopped"] or "finished"
        lines.append(
            f"`{r['id']}` **{r['kind']}** <@{r['target']}> — "
            f"{r['fired']}/{r['passes']} every {int(r['interval'])}s ({state})"
        )
        if r["last_error"]:
            lines.append(f"  last error: {r['last_error']}")
    engine.reply(channel_id, message_id, "\n".join(lines))


def mute(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+mute <user> [10m] [reason]`")
        return
    if engine.settings.muted_everyone:
        engine.reply(channel_id, message_id, "Mutes are frozen (`+nomute off` to allow).")
        return
    seconds = 600
    rest = command.args[1:]
    if rest:
        parsed = text.parse_duration(rest[0])
        if parsed:
            seconds = parsed
            rest = rest[1:]
    status = engine.rest.timeout(GUILD_ID, target, seconds, " ".join(rest) or "mute")
    engine.reply(channel_id, message_id,
                 f"<@{target}> muted for {text.human_duration(seconds)}."
                 if status in (200, 204) else f"Mute failed ({status}).")


def unmute(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+unmute <user>`")
        return
    status = engine.rest.untimeout(GUILD_ID, target, "unmute")
    engine.reply(channel_id, message_id,
                 f"<@{target}> unmuted." if status in (200, 204) else f"Unmute failed ({status}).")


def nomute(engine, command, user_id, message_id, channel_id, roles):
    _switch(engine, command, message_id, channel_id, "nomute",
            engine.settings.muted_everyone,
            lambda v: setattr(engine.settings, "muted_everyone", v))


def takeall(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+takeall <user>`")
        return
    engine.mod.snapshot(target)
    removed, skipped = engine.mod.strip_roles(target, keep=(ROLE_ETERNAL,))
    engine.reply(
        channel_id, message_id,
        f"**Roles removed from** <@{target}>\n"
        f"Removed: {', '.join(removed) if removed else 'none'}\n"
        f"Kept: {', '.join(skipped) if skipped else 'none'}\n"
        f"Snapshot saved — `+restore <user>` puts them back.",
    )


def recover(engine, command, user_id, message_id, channel_id, roles):
    status = engine.rest.add_role(GUILD_ID, user_id, ROLE_CO_OWNER, "recover")
    engine.reply(channel_id, message_id,
                 "Co owner granted." if status in (200, 204) else f"Failed ({status}).")


def snapshot(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+snapshot <user>`")
        return
    roles_saved = engine.mod.snapshot(target)
    if roles_saved is None:
        engine.reply(channel_id, message_id, "Member not found.")
        return
    engine.store.save()
    engine.reply(channel_id, message_id, f"Saved {len(roles_saved)} role(s) for <@{target}>.")


def restore(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+restore <user>`")
        return
    if not engine.store.snapshots.get(str(target)):
        engine.reply(channel_id, message_id, "No snapshot for that member.")
        return
    added, failed = engine.mod.restore(target)
    engine.reply(
        channel_id, message_id,
        f"Restored {len(added)} role(s) to <@{target}>"
        + (f". Failed: {', '.join(failed)}" if failed else "."),
    )


def strikes(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command) or user_id
    row = engine.store.get_strikes(target)
    if not row:
        engine.reply(channel_id, message_id, f"<@{target}> has no strikes.")
        return
    body = ", ".join(f"{kind}={count}" for kind, count in sorted(row.items()))
    engine.reply(channel_id, message_id, f"<@{target}> — {body}")


def clearstrikes(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+clearstrikes <user>`")
        return
    engine.store.clear_strikes(target)
    engine.store.save()
    engine.reply(channel_id, message_id, f"Strikes cleared for <@{target}>.")


def purge(engine, command, user_id, message_id, channel_id, roles):
    count = 20
    if command.args and command.args[0].isdigit():
        count = min(int(command.args[0]), 100)
    recent = engine.rest.messages(channel_id, limit=count)
    removed = 0
    for row in recent:
        if engine.rest.delete(channel_id, int(row["id"])) in (200, 204):
            removed += 1
    engine.send(channel_id, f"Purged {removed} message(s).")


def say(engine, command, user_id, message_id, channel_id, roles):
    if not command.text:
        engine.reply(channel_id, message_id, "Say what? `+say <text>`")
        return
    engine.send(channel_id, command.text)
    engine.rest.delete(channel_id, message_id)


def whois(engine, command, user_id, message_id, channel_id, roles):
    target = engine.target(command) or user_id
    member = engine.rest.member(GUILD_ID, target)
    if not member:
        engine.reply(channel_id, message_id, "Member not found.")
        return
    user = member.get("user", {})
    roles = [engine.mod.role_name(int(r)) for r in member.get("roles", [])]
    joined = (member.get("joined_at") or "")[:10]
    created = ""
    engine.reply(channel_id, message_id, "\n".join([
        f"**{user.get('username', target)}** (`{target}`)",
        f"Joined {joined}",
        f"Roles ({len(roles)}): {', '.join(roles) if roles else 'none'}",
        f"Strikes: {engine.store.get_strikes(target) or 'none'}",
    ]))


def tempownership(engine, command, user_id, message_id, channel_id, roles):
    """`+Temp Ownership @user [minutes]` - Lynx only.

    Granting is not the same as being trusted: the tier check in the engine
    treats a live grant as owner, and the sweeper takes the role back when the
    deadline passes, including across a restart.
    """
    if command.args and command.args[0].lower() in ("end", "stop", "off"):
        ok, message = engine.tempown.revoke()
        engine.reply(channel_id, message_id, message)
        return
    if command.args and command.args[0].lower() in ("status", "who"):
        tempownership_status(engine, command, user_id, message_id, channel_id, roles)
        return
    target = user_id_from(command.args[0]) if command.args else None
    if not target:
        engine.reply(channel_id, message_id,
                     "Usage: `+Temp Ownership @user [minutes]` (default 10).")
        return
    minutes = DEFAULT_MINUTES
    if len(command.args) > 1:
        try:
            minutes = int(command.args[1].rstrip("m"))
        except ValueError:
            engine.reply(channel_id, message_id, "Minutes must be a number.")
            return
    ok, message = engine.tempown.grant_to(target, minutes, granted_by=user_id)
    engine.reply(channel_id, message_id, message)


def tempownership_status(engine, command, user_id, message_id, channel_id, roles):
    grant = engine.tempown.grant
    if not grant or grant.expired:
        engine.reply(channel_id, message_id, "Nobody holds temporary ownership.")
        return
    engine.reply(
        channel_id, message_id,
        f"<@{grant.user_id}> holds temporary ownership, "
        f"{grant.seconds_left // 60}m {grant.seconds_left % 60}s left.",
    )

# Roles that a bankruptcy must never take, whoever asks. The owner keeps the
# guild; taking Owner👑 would leave the server unadministrable and no recovery
# path exists, because the bot cannot grant a role above itself.
PROTECTED = (OWNER_ID, LYNX_ID, ARCEUS_ID)


def bankrupt(engine, command, user_id, message_id, channel_id, roles):
    """`+bankrupt @user` - strip every role the bot can take, then tell them.

    Any tier may run it, which is why the target list is guarded: without this
    a moderator could bankrupt the owner and there would be no way back.
    """
    if command.args and command.args[0].lower() in ("recover", "restore", "undo"):
        return bankrupt_recover(
            engine, replace(command, args=command.args[1:]),
            user_id, message_id, channel_id, roles,
        )

    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id,
                     "Who? `+bankrupt @user`  |  `+bankrupt recover @user`")
        return
    if target in PROTECTED:
        engine.reply(channel_id, message_id,
                     f"<@{target}> is a protected operator and cannot be bankrupted.")
        return
    if target == user_id:
        engine.reply(channel_id, message_id, "You cannot bankrupt yourself.")
        return
    if target == BOT_ID:
        engine.reply(channel_id, message_id, "I am not going to bankrupt myself.")
        return

    # Every tier may run this, so a member must not be able to strip staff.
    # A plain member may bankrupt another plain member; only an owner-tier
    # caller may touch a moderator.
    actor_tier = engine.tier_of(user_id, roles)
    target_tier = engine.tier_of(target, engine.roles_for(target, {}))
    if target_tier != "user" and TIER_ORDER[actor_tier] > TIER_ORDER["owner"]:
        engine.reply(channel_id, message_id,
                     f"<@{target}> is staff - only an owner can bankrupt them.")
        return

    removed, kept, taken = engine.mod.bankrupt(target, actor_id=user_id)
    if not removed and not taken:
        engine.reply(channel_id, message_id,
                     f"<@{target}> had no roles I am allowed to remove."
                     + (f" Kept: {', '.join(kept)}" if kept else ""))
        return

    delivered = engine.rest.dm(
        target,
        "**Your roles in ᴇᴛᴇʀɴᴀʟ have been removed.**\n"
        "A Freehands moderator can give them back with `+bankrupt recover @you`.\n"
        f"Removed: {', '.join(removed)}",
    )
    engine.reply(
        channel_id, message_id,
        f"**Bankrupt:** <@{target}>\n"
        f"Removed: {', '.join(removed) if removed else 'none'}\n"
        f"Kept: {', '.join(kept) if kept else 'none'}\n"
        f"Notified: {'yes, by DM' if delivered else 'no - their DMs are closed'}\n"
        f"Undo with `+bankrupt recover @user`.",
    )


def demote(engine, command, user_id, message_id, channel_id, roles):
    """`+demote @user <reason>` - strip every role, tell them why, tell the owner.

    Unlike `+bankrupt` this is an owner-tier action with a stated reason, because
    the point is a consequence the server can point at later, not a reversible
    prank. The roles are snapshotted first so `+restore` can still undo it.
    """
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id,
                     "Who? `+demote @user <reason>` - the reason is required.")
        return
    reason = " ".join(command.args[1:]).strip()
    if not reason:
        engine.reply(channel_id, message_id,
                     "A reason is required: `+demote @user <reason>`.")
        return
    if target in PROTECTED:
        engine.reply(channel_id, message_id,
                     f"<@{target}> is a protected operator and cannot be demoted.")
        return
    if target == user_id:
        engine.reply(channel_id, message_id, "You cannot demote yourself.")
        return
    if target == BOT_ID:
        engine.reply(channel_id, message_id, "I am not going to demote myself.")
        return

    member = engine.rest.member(GUILD_ID, target) or {}
    name = (member.get("nick") or (member.get("user") or {}).get("username")
            or str(target))
    engine.mod.snapshot(target)
    removed, kept = engine.mod.strip_roles(target, keep=())
    if not removed:
        engine.reply(channel_id, message_id,
                     f"<@{target}> had no roles I am allowed to remove."
                     + (f" Kept: {', '.join(kept)}" if kept else ""))
        return

    delivered = engine.rest.dm(
        target,
        "**Your roles in ᴇᴛᴇʀɴᴀʟ have been removed.**\n"
        f"**Reason:** {reason}\n"
        "An owner can restore them with `+restore @you`.",
    )
    # The owner is told in the channel the command ran in, and by DM, because a
    # demotion is exactly the kind of action that should not be missed.
    engine.send(
        channel_id,
        f"<@{OWNER_ID}> **Demotion:** <@{target}> (`{name}`)\n"
        f"**Reason:** {reason}\n"
        f"**Removed:** {', '.join(removed) if removed else 'none'}\n"
        f"**Kept:** {', '.join(kept) if kept else 'none'}\n"
        f"**Notified:** {'yes, by DM' if delivered else 'no - their DMs are closed'}\n"
        f"Undo with `+restore @user`.",
        allowed_mentions={"parse": [], "users": [str(OWNER_ID)]},
    )
    engine.rest.dm(
        OWNER_ID,
        f"**Demotion in ᴇᴛᴇʀɴᴀʟ**\n"
        f"<@{target}> (`{name}`) had their roles removed.\n"
        f"**Reason:** {reason}\n"
        f"**Removed:** {', '.join(removed)}\n"
        f"**By:** <@{user_id}>",
    )


def bankrupt_recover(engine, command, user_id, message_id, channel_id, roles):
    """`+bankrupt recover @user` - moderator or owner only.

    The recovery must be at least as privileged as the bankruptcy, otherwise
    anyone could undo a moderator's action.
    """
    if TIER_ORDER[engine.tier_of(user_id, roles)] > TIER_ORDER["mod"]:
        engine.reply(channel_id, message_id,
                     "Only a moderator or the owner can recover roles.")
        return
    target = engine.target(command)
    if not target:
        engine.reply(channel_id, message_id, "Who? `+bankrupt recover @user`")
        return
    if not engine.store.bankrupt.get(str(target)):
        engine.reply(channel_id, message_id, f"No bankruptcy on record for <@{target}>.")
        return
    added, failed = engine.mod.unbankrupt(target)
    engine.reply(
        channel_id, message_id,
        f"**Recovered** <@{target}>: {', '.join(added) if added else 'nothing restored'}"
        + (f"\nFailed: {', '.join(failed)}" if failed else ""),
    )
