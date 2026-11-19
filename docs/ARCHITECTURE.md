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

## State

`bot/state.json` holds settings, strikes, role snapshots, the known-ban cache and
the last 200 incidents. Writes are atomic (`mkstemp` then `os.replace`) and
coalesced to at most one every five seconds unless forced.

## Testing

`bot/tests/test_core.py` covers the pure logic: code matching, command parsing,
text rules, the vault round trip, and store persistence. It also asserts that no
plaintext token exists in the package.

`bot/tests/test_engine.py` drives the real engine with a `FakeRest`, so routing,
permissions, code alerts, auto-moderation and anti-ban all execute as they do in
production.
