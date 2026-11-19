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

`ops.py` owns one channel, `#ops-command`. Sensitive codes alert there instead of
in open chat, and the Dyllan watch writes there too.

Access is **three member overwrites and nothing else** - owner, Arceus, Lynx, plus
the bot so it can post. There is deliberately no access role:

- a role can be handed to someone else, and whoever holds it inherits the
  channel; a member overwrite belongs to exactly one person.
- an access role also outranks a member deny in Discord's resolution order, so a
  stray grant could reopen the channel even after a member was removed.

`_lock()` re-asserts all four overwrites on every start and deletes any overwrite
that is not on the list, so a manual grant is temporary by construction rather
than by discipline.

### What it cannot do

The `Administrator` permission bypasses channel overwrites completely. Any member
holding it can read the channel no matter what the overwrites say. In this guild
thirteen roles carry it, including `THE KING👑`, `Co owner`, `Administrator` and
`Kostas`. That is a Discord invariant, not a bug in this code, and no API call
can override it. `+ops audit` reports it honestly. The only remedy is for the
owner to remove `Administrator` from roles that do not need it.

Defence in depth, for anyone who does get in: every message is checked against
`ALLOWED_OPS` before commands or codes are parsed, so a non-operator cannot run
anything from inside. Their messages are purged and the operators are told.

Whether their access was actually removed is decided by `can_view()`, not by the
`DELETE` status: Discord answers `200` to an overwrite deletion even when no
overwrite existed, so the status proves nothing. `can_view()` resolves the
permission bits the way Discord does - union the base permissions, short-circuit
on `Administrator`, then apply the `@everyone`, role and member overwrites. When
a member can still view the channel afterwards, the notice says `FAILED` and the
bot escalates to a kick, which needs no permission hierarchy.

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
