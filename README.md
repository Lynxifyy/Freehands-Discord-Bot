<p align="center">
  <img src="assets/icon.png" alt="Freehands" width="128" height="128">
</p>

<h1 align="center">Freehands</h1>

<p align="center">
  The <strong>Eternal</strong> guild's operations bot.<br>
  Code sense, ban protection, and moderation that answers in under a second.
</p>

<p align="center">
  <img src="assets/banner.png" alt="Freehands banner" width="600">
</p>

---

## What it does

**Code sense.** Say `code 8` in chat and the bot pings Arceus and the owner with
the eyes emoji - code 8 means *suspected spy*. Say `code 10`, *I'm getting found
out*, and the alert goes out while the trigger message is deleted and the bot
stays quiet instead of replying in the channel. Twelve codes ship by default and
[`bot/codes.json`](bot/codes.json) can add or override any of them.

**Ban protection.** Anti-ban lifts every ban this bot did not issue, from three
independent paths: a periodic sweep, the audit log, and the live ban event.
People on the keep-banned list are exempt and are re-banned if their ban
disappears.

**Speed.** The bot holds a gateway websocket, so a message is handled the moment
it is sent instead of on a poll tick. REST calls remember Discord's per-route
rate-limit buckets, so a burst of moderation waits instead of failing.

**Moderation.** Escalating slur strikes (warn, then mute, then an operator vote),
spam timeouts, invite blocking, raid detection with auto-lockdown, role snapshots
with restore, and a three-vote channel lockdown.

## Quick start

```bash
git clone https://github.com/Lynxifyy/Freehands-Discord-Bot.git
cd Freehands-Discord-Bot

python3 -m unittest discover -s bot/tests -t bot   # 67 tests, no network
python3 scripts/doctor.py                          # read-only health check
./scripts/run.sh                                   # start the bot
```

No dependencies. Python 3.10+ and the standard library are enough.

## Configuration

| What | Where |
| --- | --- |
| Token | `FH_TOKEN` env, then `bot/.token`, then the embedded masked blob |
| Guild and role IDs | `bot/freehands/config.py` |
| Codebook | `bot/codes.json` (overrides the built-in table) |
| Runtime switches | `bot/state.json`, written by `+antiban`, `+mod`, `+codesense` |
| Log level | `FH_LOG=DEBUG` |
| Gateway off | `FH_GATEWAY=0` (falls back to REST polling) |

The token is stored XOR-masked and split across four fragments in
`bot/freehands/vault.py`, so no literal credential exists in the tree.
Regenerate it with:

```bash
python3 scripts/encode_token.py --from-file bot/.token
python3 scripts/encode_token.py --check
```

Set `FH_TOKEN` in production and keep the embedded blob as the fallback for a
fresh container.

## Commands

Prefix is `+`. See [docs/COMMANDS.md](docs/COMMANDS.md) for every command and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit.

```
+help                    what you can run
+codes                   the codebook
+antiban on|off          ban protection
+keepbanned add|remove   anti-ban exceptions
+mute <user> [10m]       timeout
+takeall <user>          strip roles (snapshots first)
+restore <user>          put them back
+lockvote yes            vote to lock the channel
```

## Codes

| Code | Meaning | What happens |
| --- | --- | --- |
| 1 | All clear | acknowledged, no ping |
| 3 | Request backup | pings owner and Arceus |
| 4 | Comms compromised | pings, deletes the trigger |
| 8 | Suspected spy | pings owner and Arceus with the eyes emoji |
| 9 | Cover blown | critical, deletes the trigger |
| 10 | Getting found out | critical, deletes the trigger, goes quiet |
| 12 | Full lockdown | critical, locks the channel |

Codes also match their phrases: "there's a spy" raises code 8.

## Notes on the Discord app

`GUILD_MEMBERS` and `MESSAGE_CONTENT` are privileged intents. This app does not
have them enabled, so the bot identifies without them and keeps a
content-hydration path that re-reads each message over REST, which is not
intent-gated. If the app is granted them later, the bot uses them without a code
change.

To use member events (`MEMBER_ADD`, raid detection) enable **Server Members
Intent** in the developer portal. To drop the extra REST read per message,
enable **Message Content Intent**.
