# Architecture

```
                    Discord
                       |
        +--------------+---------------+
        |                              |
   gateway.py                      rest.py
   (websocket)                 (HTTPS + buckets)
        |                              |
        +--------------+---------------+
                       |
                    engine.py
            routing, codes, automod
               |            |
        codebook.py     cmd_impl.py
         (codes)        (commands)
                       |
                   moderation.py
              roles, snapshots, anti-ban
                       |
                   store.py
                 (state.json)
```

## Modules

| Module | Responsibility |
| --- | --- |
| `config.py` | Guild, role and user IDs, intents, `Settings` |
| `vault.py` | Token resolution and the masked credential blob |
| `log.py` | Logger setup and the `Stats` counters |
| `store.py` | Atomic JSON persistence for settings, strikes, snapshots, incidents |
| `rest.py` | One `request()` that understands rate limits, plus typed helpers |
| `gateway.py` | Hand-rolled RFC 6455 client: hello, heartbeat, identify, resume |
| `codebook.py` | Code table, matching, alert rendering |
| `text.py` | Slur, invite, spam, raid and duration rules (all pure) |
| `commands.py` | `+cmd` parsing, registry, aliases, suggestions, tiers |
| `moderation.py` | Hierarchy checks, snapshots, anti-ban, keep-banned, lockdown |
| `engine.py` | Event routing, auto-moderation, dispatch |
| `cmd_impl.py` | The command bodies and the permission table |
| `runner.py` | Wiring, gateway startup, poll fallback, maintenance loop |

## Why the event path looks like this

`MESSAGE_CONTENT` is a privileged intent and this app does not have it. Without
it the gateway still delivers `MESSAGE_CREATE`, but `content` is empty. The
engine therefore hydrates content over REST for blank messages:

```python
if not content and not msg.get("_hydrated"):
    content = self._hydrate_content(channel_id, message_id) or ""
```

`GET /channels/{id}/messages/{id}` is not intent-gated, so this recovers the text
at the cost of one extra request per message. If the app is granted the intent,
content arrives populated and the hydration branch never runs.

`GUILD_MEMBERS` is missing too, so `MEMBER_ADD` never fires and the bot reads
roles from the message payload instead, falling back to a cached REST lookup.
Identify sends only non-privileged intents; if Discord closes with `4014` the
gateway strips the privileged bits and retries immediately rather than looping.

## Rate limits

Each route keeps its own bucket, updated from `X-RateLimit-Remaining` and
`X-RateLimit-Reset-After`. A 429 sets a global hold from `retry_after`. 5xx and
transport errors retry with exponential backoff. This is what keeps a role strip
over twenty roles from failing halfway through.

## Anti-ban

Three independent paths, all skipping the keep-banned set:

1. **Sweep** every maintenance tick, plus once at startup.
2. **Audit log** polling for `BAN_ADD` entries newer than the last check.
3. **Live event** on `GUILD_BAN_ADD`, reversed immediately.

`known_bans` is seeded at startup so pre-existing bans are not fought over on
every restart. `enforce_keep_banned` re-applies a ban whenever an exception
member's ban goes missing.

## The private operator channel

`ops.py` owns one channel, `#ops-command`, and the `ops-access` role that gates
it. Sensitive codes alert there instead of in open chat, and the Dyllan watch
writes there too.

Access is **one role**, not a per-member allow list, because of how Discord
resolves permissions:

- the `Administrator` permission bypasses channel overwrites completely. No
  overwrite, deny or member-level entry can hide a channel from an admin.
- a member-level deny also loses to any role that grants the permission, so a
  per-member allow list would look private without being private.

So the channel denies `@everyone`, and allows exactly two principals: the bot
and the `ops-access` role. That role carries no permissions of its own; it is
only a key. `ensure()` grants it to the owner, Arceus and Lynx and re-asserts
every overwrite on each start, which is what makes a manual permission edit
temporary.

What that does **not** buy is secrecy from administrators. `+ops audit` reports
this honestly rather than implying the channel is airtight. The only fix is for
the owner to remove `Administrator` from the roles that do not need it, which the
bot cannot and should not do by itself.

Defence in depth, for anyone who does get in: every message in the channel is
checked against `ALLOWED_OPS` before anything else runs. A non-operator's
overwrite is removed, their messages are purged, and the operators are told. If
the removal fails because a higher role grants access, the bot escalates to a
kick, which needs no permission hierarchy.

## State

`bot/state.json` holds settings, strikes, role snapshots, the known-ban cache,
the ops channel and gate-role ids, the armed state of the Dyllan watch, and the
last 200 incidents. Writes are atomic (`mkstemp` then `os.replace`) and
coalesced to at most one every five seconds unless forced.

## Testing

`bot/tests/test_core.py` covers the pure logic: code matching, command parsing,
text rules, the vault round trip, and store persistence. It also asserts that no
plaintext token exists in the package.

`bot/tests/test_engine.py` drives the real engine with a `FakeRest`, so routing,
permissions, code alerts, auto-moderation and anti-ban all execute as they do in
production.
