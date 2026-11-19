"""Guild constants and runtime settings.

IDs are the 𝘌𝘵𝘦𝘳𝘯𝘢𝘭 guild's real snowflakes so a restart needs no discovery
round-trip. Anything that can change at runtime lives in `Settings`, which is
persisted by the store.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

GUILD_ID = 1570966200521990224
MAIN_CHAT_ID = 1570966202573000798
BOT_ID = 1568005572769480704

# People
OWNER_ID = 1310733783653154816
ARCEUS_ID = 1523669026201669753
LYNX_ID = 1002131928775925840
BUM_ID = 1566512766066491642

# People the bot watches or keeps out
WATCH_ID = 1522388014418886746        # Dyllan / Mysterious Stranger
KEEP_BANNED_ID = 1535047765032173668  # 『NS』Veil

# The only three people who may see the private operator channel. Written as
# per-member overwrites, not a role, so nobody can be handed access by being
# given a role. Dyllan is deliberately absent: he is watched, not an operator.
ALLOWED_OPS = frozenset({OWNER_ID, ARCEUS_ID, LYNX_ID})

OPS_CHANNEL_NAME = "ops-command"
OPS_CHANNEL_TOPIC = (
    "Private operator channel. Code alerts land here. "
    "Anyone who is not an operator is removed automatically."
)

# Roles
ROLE_OWNER = 1571904843659092099
ROLE_CO_OWNER = 1571904304925642903
ROLE_ADMIN = 1570969297226834091
ROLE_MOD = 1570969769245413396
ROLE_HELPER = 1571691525400699041
ROLE_OG = 1571569052185534555
ROLE_ETERNAL = 1570967921096785990
ROLE_AUTOROLE = 1570967389598785609
ROLE_UNMUTEABLE = 1572069341883797554

# Roles that carry operator authority on top of the hard-coded user ids.
OPERATOR_ROLES = (ROLE_OWNER, ROLE_CO_OWNER, ROLE_ADMIN)
MOD_ROLES = (ROLE_MOD, ROLE_HELPER)

# Slurs are enforced for everyone except the people who are "of culture".
SLUR_EXEMPT = frozenset({OWNER_ID, LYNX_ID, ARCEUS_ID, BUM_ID})

PREFIX = "+"

# Channels the bot reads and acts in. Hydrating blank gateway content costs one
# REST read per message, so it is scoped to these rather than every channel.
# The ops channel joins this set at runtime once it exists.
# Override with FH_CHANNELS="123,456".
TRACKED_CHANNELS = frozenset({MAIN_CHAT_ID})

# Intents. GUILDS | GUILD_MODERATION | GUILD_MESSAGES are non-privileged.
# GUILD_MEMBERS and MESSAGE_CONTENT are privileged: the app must have them
# enabled in the developer portal, otherwise Identify closes with 4014 and
# guild message content arrives empty. `gateway` downgrades automatically and
# `engine` re-reads content over REST, which is not intent-gated.
INTENTS = (1 << 0) | (1 << 9) | (1 << 2)
INTENT_GUILD_MEMBERS = 1 << 1
INTENT_MESSAGE_CONTENT = 1 << 15

API = "https://discord.com/api/v10"
GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"


@dataclass
class Settings:
    """Mutable runtime switches, persisted between restarts."""

    anti_ban: bool = True
    keep_banned: set[int] = field(default_factory=lambda: {KEEP_BANNED_ID})
    moderation_enabled: bool = True
    automod: bool = True
    watch_enabled: bool = True
    codes_enabled: bool = True
    lockdown: bool = False
    punish_strikes_to_lock: int = 3
    spam_window: float = 6.0
    spam_limit: int = 6
    raid_joins: int = 8
    raid_window: float = 20.0
    muted_everyone: bool = False
    ops_channel_id: int = 0
    # Dyllan watch. `watch_enabled` is the master switch for the feature;
    # `watch_armed` is what code 11 turns on and what actually logs his traffic.
    watch_armed: bool = False
    # A live temporary-ownership grant, or None. Kept here so it survives a
    # restart with its original deadline instead of becoming permanent.
    temp_grant: dict | None = None

    def to_json(self) -> dict:
        return {
            "anti_ban": self.anti_ban,
            "keep_banned": sorted(self.keep_banned),
            "moderation_enabled": self.moderation_enabled,
            "automod": self.automod,
            "watch_enabled": self.watch_enabled,
            "codes_enabled": self.codes_enabled,
            "lockdown": self.lockdown,
            "punish_strikes_to_lock": self.punish_strikes_to_lock,
            "spam_window": self.spam_window,
            "spam_limit": self.spam_limit,
            "raid_joins": self.raid_joins,
            "raid_window": self.raid_window,
            "muted_everyone": self.muted_everyone,
            "ops_channel_id": self.ops_channel_id,
            "watch_armed": self.watch_armed,
            "temp_grant": self.temp_grant,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Settings":
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in (data or {}).items() if k in known}
        if "keep_banned" in kwargs:
            kwargs["keep_banned"] = set(int(x) for x in kwargs["keep_banned"])
        for key in ("ops_channel_id",):
            if key in kwargs:
                kwargs[key] = int(kwargs[key] or 0)
        return cls(**kwargs)


def env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")
