# Commands

Prefix `+`. A command also works as `<@Freehands> +command`.

Tiers: **user** anyone, **mod** moderator roles, **owner** owner, Arceus, Lynx,
or any of the operator roles (Owner, Co owner, Administrator).

## Information

| Command | Tier | What it does |
| --- | --- | --- |
| `+help` | user | Commands you are allowed to run, plus the code list |
| `+ping` | user | Round-trip latency |
| `+stats` | user | Uptime, counters, and the live switch states |
| `+codes` | user | The codebook with severity and pings |
| `+incidents [n]` | mod | Recent code hits, newest last |
| `+question <text>` | user | Posts a question and pings Lynx for `+answer` |
| `+whois <user>` | mod | Join date, roles, strikes |

## Switches

| Command | Tier | What it does |
| --- | --- | --- |
| `+antiban on\|off` | owner | Arm or disarm ban protection |
| `+keepbanned add\|remove <user>` | owner | Anti-ban exceptions (alias `+kb`) |
| `+mod on\|off` | owner | Master moderation switch |
| `+automod on\|off` | owner | Slurs, spam, invites, punish requests |
| `+codesense on\|off` | owner | Code detection |
| `+watch on\|off` | owner | Watching the flagged member |
| `+nomute on\|off` | owner | Freeze every mute |

`+antiban` with no argument reports the current state. Arming it runs a sweep
immediately and reports how many bans were lifted.

## Moderation

| Command | Tier | What it does |
| --- | --- | --- |
| `+ban <user> [reason]` | owner | Refused while anti-ban is armed |
| `+unban <user>` | owner | Also clears keep-banned and the known-ban cache |
| `+kick <user>` | owner | Kick |
| `+mute <user> [10m] [reason]` | mod | Timeout; duration accepts `s m h d w` |
| `+unmute <user>` | mod | Clear a timeout |
| `+takeall <user>` | owner | Snapshot, then strip every role except Eternal |
| `+snapshot <user>` | owner | Save the current role set |
| `+restore <user>` | owner | Re-apply the saved role set |
| `+strikes <user>` | mod | Strike counters by kind |
| `+clearstrikes <user>` | owner | Reset all strikes |
| `+purge [n]` | mod | Delete the last n messages (max 100) |
| `+say <text>` | owner | Speak as the bot, then delete the command |

## Votes and approvals

| Command | Tier | What it does |
| --- | --- | --- |
| `+approve` | owner | Ban the pending slur offender |
| `+deny` | owner | Clear the pending request |
| `+lockvote yes\|no` | owner | Three yes votes lock the channel; one no cancels |
| `+lock` / `+unlock` | owner | Lock or unlock the main channel directly |

## Codes

Codes need no prefix. Say the number, or the phrase.

| Code | Title | Severity | Pings | Deletes trigger |
| --- | --- | --- | --- | --- |
| 1 | All clear | low | - | no |
| 2 | Moving position | low | - | no |
| 3 | Request backup | medium | owner, Arceus | no |
| 4 | Comms compromised | high | owner, Arceus | yes |
| 5 | Target acquired | medium | owner | no |
| 6 | Extraction needed | high | owner, Arceus | no |
| 7 | Going dark | medium | - | yes |
| 8 | Suspected spy | high | owner, Arceus | no |
| 9 | Cover blown | critical | owner, Arceus | yes |
| 10 | Getting found out | critical | owner, Arceus | yes |
| 11 | Silent alarm | high | owner, Arceus | yes |
| 12 | Full lockdown | critical | owner, Arceus | yes (locks channel) |

Matching accepts `code 8`, `code-8`, `code: 8`, `code #8`, `code8`, `code eight`,
and `code VIII`. A bare number never triggers, so ordinary chatter stays quiet.

Add codes in `bot/codes.json`:

```json
{
  "codes": [
    {
      "number": 13,
      "title": "New code",
      "meaning": "What it means",
      "severity": "high",
      "ping_owner": true,
      "ping_arceus": false,
      "silence": true,
      "response": "What the bot says",
      "aliases": ["new code phrase"]
    }
  ]
}
```
