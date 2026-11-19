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
| `+ops` | owner | Private channel status |
| `+ops create` | owner | Create or find the private channel |
| `+ops lock` | owner | Force it back to the three-person allow-list |
| `+ops audit` | owner | Show who can actually read it |
| `+dyllan on\|off` | owner | Arm or disarm the watch |
| `+Temp Ownership @user [min]` | **Lynx only** | Lend ownership for 10 minutes |
| `+Temp Ownership end` | **Lynx only** | Take it back immediately |
| `+Temp Ownership status` | **Lynx only** | Who holds it, and how long is left |
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

`Where` is the channel the alert lands in: **chat** is `#main-chat`,
**private** is the operator channel.

| Code | Title | Severity | Pings | Deletes trigger | Where |
| --- | --- | --- | --- | --- | --- |
| 1 | All clear | low | - | no | chat |
| 2 | Moving position | low | - | no | chat |
| 3 | Request backup | medium | owner, Arceus | no | chat |
| 4 | Comms compromised | high | owner, Arceus | yes | private |
| 5 | Target acquired | medium | owner | no | chat |
| 6 | Extraction needed | high | owner, Arceus | no | chat |
| 7 | Going dark | medium | - | yes | chat |
| 8 | Suspected spy | high | owner, Arceus | no | chat |
| 9 | Cover blown | critical | owner, Arceus | yes | private |
| 10 | Getting found out | critical | owner, Arceus | yes | private |
| 11 | Dyllan's back | high | owner, Arceus | no | private |
| 12 | Full lockdown | critical | owner, Arceus | yes (locks channel) | private |
| 13 | Raid incoming | critical | owner, Arceus | no | private |
| 14 | Leak | critical | owner, Arceus | yes (purges 10m) | private |
| 15 | Impersonation | high | owner, Arceus | no | private |
| 16 | Admin abuse | critical | owner, Arceus | no | private |
| 17 | DM compromise | critical | owner, Arceus | yes | private |
| 18 | Evidence secured | low | owner | no | chat |
| 19 | Radio silence | high | owner, Arceus | yes | private |
| 20 | Server compromised | critical | owner, Arceus | no | private |

### Bankrupt

`+bankrupt @user` strips every role the bot is allowed to remove, then DMs the
member to tell them their roles are gone and how to get them back. Any tier can
run it. `+bankrupt recover @user` puts back exactly what was taken - moderators
and owners only.

It is designed to be reversible, so the guards matter:

- the bot never strips `@Eternal`, the guild's floor role; removing it would take
  the member out of the server rather than demote them
- `@Owner`, Lynx and Arceus are **protected targets** - no one can bankrupt them,
  at any tier. Taking `Owner👑` would leave the server unadministrable, and the
  bot cannot grant that role back because it sits above the bot
- you cannot bankrupt yourself or the bot
- a plain member cannot bankrupt staff; only an owner-tier caller can
- only roles that were actually removed are recorded, so a recovery never claims
  to have restored something it did not

The record is written to `state.json` immediately, so a recovery still works
after a restart. A bankruptcy that removed nothing is not recorded at all.

Recovery needs the role to still exist and still be below the bot. If a role was
deleted or moved above the bot in the meantime, the reply lists it as failed
rather than silently skipping it.

### Temporary ownership

`+Temp Ownership @user` gives that member operator authority for ten minutes.
Only Lynx can run it - not the owner, not Arceus, nobody else. Pass a number of
minutes to change the duration: `+Temp Ownership @user 30`.

It works by granting `Co owner`, which is the highest role the bot can assign.
It cannot grant `Owner👑` because that role sits above the bot, and Discord
refuses to grant a role above the granter. The reply says so if Discord refuses.

The deadline is stored, not just the role, so the grant expires even if the bot
restarts in between. A second grant takes the first one back before applying.
`+Temp Ownership end` revokes immediately.

### Code 11 arms the watch

Code 11 means Dyllan is back. It does two things beyond alerting: it **arms the
watch**, and from then on every message he sends is copied into the private
channel with the rules it tripped (`slur`, `invite`, `mass mention`,
`caps flood`, `punish request`). The watch stays armed across restarts until you
turn it off with `+dyllan off`.

Matching accepts `code 8`, `code-8`, `code: 8`, `code #8`, `code8`, `code eight`,
and `code VIII`. A bare number never triggers, so ordinary chatter stays quiet.

`ops: true` sends the alert to the private channel instead of open chat.
`arm_watch: true` starts watching the flagged member.

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
      "ops": true,
      "arm_watch": false,
      "aliases": ["new code phrase"]
    }
  ]
}
```
