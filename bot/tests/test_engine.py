"""Behaviour tests for the engine.

A `FakeRest` stands in for the HTTP layer — the only external boundary — so the
real routing, permission, code and auto-mod code paths run exactly as they do
in production.
"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from freehands.codebook import Codebook
from freehands.config import (
    ARCEUS_ID,
    BOT_ID,
    CODE8_MEMBERS,
    GUILD_ID,
    LYNX_ID,
    MAIN_CHAT_ID,
    OWNER_ID,
    ROLE_CO_OWNER,
    ROLE_MOD,
    DYLLAN_ID,
    ROLE_ETERNAL,
    SPY_ID,
    WATCH_ID,
)
from freehands.engine import Engine
from freehands.ops import AlertRoom
from freehands.moderation import RoleInfo
from freehands.store import Store


class FakeRest:
    """In-memory stand-in for `freehands.rest.Rest`."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.replies: list[dict] = []
        self.deleted: list[tuple[int, int]] = []
        self.reactions: list[tuple[int, int, str]] = []
        self.timeouts: list[tuple[int, int]] = []
        self.unbans: list[int] = []
        self.ban_calls: list[tuple[int, str | None]] = []
        self.role_removed: list[tuple[int, int]] = []
        self.role_added: list[tuple[int, int]] = []
        self.dms: list[dict] = []
        self.dm_open = True
        self.members: dict[int, dict] = {}
        self.ban_rows: list[dict] = []
        self.audit_rows: list[dict] = []
        self.channel_rows: list[dict] = []
        self.channel_rows_by_id: dict[int, dict] = {}
        self.created_channels: list[dict] = []
        self.overwrites: dict[tuple[int, int], tuple[int, str, str]] = {}
        self.overwrite_deletes: list[tuple[int, int]] = []
        self.kicks: list[int] = []
        self.role_rows: list[dict] = []
        self.created_roles: list[dict] = []
        self.status = 204

    # -- reads ------------------------------------------------------------
    def me(self):
        return {"id": str(BOT_ID), "username": "Freehands"}

    def member(self, guild_id, user_id):
        row = self.members.get(user_id)
        return row

    # -- direct messages ---------------------------------------------------
    def open_dm(self, user_id):
        return 900000000000000000 + user_id % 1000

    def dm(self, user_id, content, **extra):
        if not self.dm_open:
            return False
        self.dms.append({"user": user_id, "content": content})
        return True

    def bans(self, guild_id):
        return self.ban_rows

    def audit(self, guild_id, action_type, limit=25):
        return self.audit_rows

    def messages(self, channel_id, limit=50, after=None):
        return []

    # -- writes -----------------------------------------------------------
    def send(self, channel_id, content="", **extra):
        self.sent.append({"channel": channel_id, "content": content, **extra})
        return {"id": str(len(self.sent)), "channel_id": str(channel_id)}

    def reply(self, channel_id, message_id, content, **extra):
        self.replies.append({"channel": channel_id, "to": message_id, "content": content, **extra})
        return {"id": str(len(self.replies))}

    def delete(self, channel_id, message_id):
        self.deleted.append((channel_id, message_id))
        return self.status

    def react(self, channel_id, message_id, emoji):
        self.reactions.append((channel_id, message_id, emoji))
        return self.status

    def typing(self, channel_id):
        return self.status

    def timeout(self, guild_id, user_id, seconds, reason=None):
        self.timeouts.append((user_id, seconds))
        return self.status

    def untimeout(self, guild_id, user_id, reason=None):
        return self.status

    def ban(self, guild_id, user_id, reason=None, delete_seconds=0):
        self.ban_calls.append((user_id, reason))
        return self.status

    def unban(self, guild_id, user_id, reason=None):
        self.unbans.append(user_id)
        return self.status

    def kick(self, guild_id, user_id, reason=None):
        self.kicks.append(user_id)
        return self.status

    def add_role(self, guild_id, user_id, role_id, reason=None):
        self.role_added.append((user_id, role_id))
        if self.status in (200, 204):
            row = self.members.setdefault(user_id, {"user": {"id": str(user_id)}, "roles": []})
            if str(role_id) not in row["roles"]:
                row["roles"].append(str(role_id))
        return self.status

    def remove_role(self, guild_id, user_id, role_id, reason=None):
        self.role_removed.append((user_id, role_id))
        if self.status in (200, 204):
            row = self.members.get(user_id)
            if row and str(role_id) in row.get("roles", []):
                row["roles"].remove(str(role_id))
        return self.status

    # -- channels ---------------------------------------------------------
    def channels(self, guild_id):
        return self.channel_rows

    def channel(self, channel_id):
        return self.channel_rows_by_id.get(channel_id)

    def create_channel(self, guild_id, name, kind=0, overwrites=None,
                       topic=None, parent_id=None, reason=None):
        self.created_channels.append(
            {"name": name, "overwrites": overwrites or [], "topic": topic}
        )
        cid = 555000000000000001
        row = {"id": str(cid), "type": 0, "name": name,
               "permission_overwrites": list(overwrites or [])}
        self.channel_rows.append({"id": str(cid), "type": 0, "name": name})
        self.channel_rows_by_id[cid] = row
        return {"id": str(cid), "name": name}

    def put_overwrite(self, channel_id, target_id, kind, allow, deny, reason=None):
        self.overwrites[(channel_id, target_id)] = (kind, allow, deny)
        row = self.channel_rows_by_id.get(channel_id)
        if row is not None:
            rows = [o for o in row["permission_overwrites"] if int(o["id"]) != target_id]
            rows.append({"id": str(target_id), "type": kind,
                         "allow": allow, "deny": deny})
            row["permission_overwrites"] = rows
        return 204

    def delete_overwrite(self, channel_id, target_id, reason=None):
        """Mirrors Discord: answers 200 even when nothing was there."""
        self.overwrite_deletes.append((channel_id, target_id))
        self.overwrites.pop((channel_id, target_id), None)
        row = self.channel_rows_by_id.get(channel_id)
        if row is not None:
            row["permission_overwrites"] = [
                o for o in row["permission_overwrites"] if int(o["id"]) != target_id
            ]
        return 200

    # -- roles ------------------------------------------------------------
    def request(self, method, route, body=None, **kw):
        if method == "GET" and route.endswith("/roles"):
            return self.role_rows
        if method == "POST" and route.endswith("/roles"):
            rid = 777000000000000001
            row = {"id": str(rid), "name": body["name"],
                   "permissions": str(body.get("permissions", "0")), "position": 1}
            self.role_rows.append(row)
            self.created_roles.append(body)
            return row
        raise AssertionError(f"unexpected request {method} {route}")

    def try_request(self, method, route, body=None, **kw):
        return self.status, None


def build_engine(tmp: str) -> tuple[Engine, FakeRest]:
    rest = FakeRest()
    store = Store(Path(tmp) / "state.json")
    engine = Engine(rest, store, Codebook())
    # The bot outranks everything in these fixtures unless a test says otherwise.
    engine.mod.roles = {
        1234: RoleInfo(1234, "1234", 1, False, 0),
        ROLE_ETERNAL: RoleInfo(ROLE_ETERNAL, "Eternal", 1, False, 0),
        ROLE_MOD: RoleInfo(ROLE_MOD, "Moderator", 5, False, 0),
    }
    engine.mod.bot_top = 100
    return engine, rest


def message(user_id: int, content: str, message_id: int = 1,
            roles: list[int] | None = None, channel_id: int | None = None) -> dict:
    return {
        "id": str(message_id),
        "channel_id": str(channel_id or MAIN_CHAT_ID),
        "content": content,
        "author": {"id": str(user_id), "username": "tester", "bot": False},
        "member": {"roles": [str(r) for r in (roles or [])]},
    }


class CodeAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_code_8_alerts_and_pings_owner_arceus_and_lynx(self):
        # Reported by someone else: the author is always in the mention list,
        # so sending as Lynx would pass even if she were never added.
        self.engine.on_message(message(999, "code 8"))
        self.assertEqual(len(self.rest.sent), 1)
        self.assertNotEqual(self.rest.sent[0]["channel"], MAIN_CHAT_ID)
        body = self.rest.sent[0]["content"]
        self.assertIn("CODE 8", body)
        self.assertIn(f"<@{OWNER_ID}>", body)
        self.assertIn(f"<@{ARCEUS_ID}>", body)
        self.assertIn(f"<@{LYNX_ID}>", body)
        self.assertIn("\N{EYES}", body)
        mentions = self.rest.sent[0]["allowed_mentions"]
        self.assertIn(str(OWNER_ID), mentions["users"])
        self.assertIn(str(ARCEUS_ID), mentions["users"])
        # The guild owner and the bot's creator are different accounts, so a
        # code that pings "the owner" has to reach Lynx as well.
        self.assertIn(str(LYNX_ID), mentions["users"])

    def test_code_10_deletes_the_trigger_message(self):
        self.engine.on_message(message(LYNX_ID, "code 10", message_id=99))
        self.assertIn((MAIN_CHAT_ID, 99), self.rest.deleted)
        self.assertIn("GETTING FOUND OUT", self.rest.sent[0]["content"])

    def test_low_severity_code_does_not_ping(self):
        self.engine.on_message(message(LYNX_ID, "code 1"))
        mentions = self.rest.sent[0]["allowed_mentions"]["users"]
        self.assertNotIn(str(OWNER_ID), mentions)

    def test_incident_is_recorded(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertEqual(self.engine.store.incidents[-1]["code"], 8)

    def test_bot_ignores_itself(self):
        row = message(BOT_ID, "code 8")
        row["author"]["bot"] = True
        self.engine.on_message(row)
        self.assertEqual(self.rest.sent, [])

    def test_code_sense_can_be_disabled(self):
        self.engine.settings.codes_enabled = False
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertEqual(self.rest.sent, [])

    def test_untracked_channel_is_ignored(self):
        row = message(LYNX_ID, "code 8")
        row["channel_id"] = "999999999999999999"
        self.engine.on_message(row)
        self.assertEqual(self.rest.sent, [])

    def test_code_12_locks_the_channel(self):
        locked: list[bool] = []
        self.engine.mod.set_channel_locked = lambda cid, state: locked.append(state) or True
        self.engine.on_message(message(LYNX_ID, "code 12"))
        self.assertEqual(locked, [True])


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_member_cannot_use_owner_command(self):
        self.engine.on_message(message(5555, "+antiban off"))
        self.assertTrue(any("permission" in r["content"] for r in self.rest.replies))
        self.assertTrue(self.engine.settings.anti_ban)

    def test_owner_can_toggle_antiban(self):
        self.engine.on_message(message(OWNER_ID, "+antiban off"))
        self.assertFalse(self.engine.settings.anti_ban)

    def test_mod_role_grants_mod_tier(self):
        self.engine.on_message(message(5555, "+strikes", roles=[ROLE_MOD]))
        self.assertTrue(self.rest.replies)
        self.assertNotIn("permission", self.rest.replies[-1]["content"])

    def test_unknown_command_suggests(self):
        self.engine.on_message(message(OWNER_ID, "+antibna"))
        self.assertIn("antiban", self.rest.replies[-1]["content"])

    def test_ban_is_refused_while_antiban_armed(self):
        self.engine.on_message(message(OWNER_ID, "+ban <@777777777777777777>"))
        self.assertIn("anti-ban", self.rest.replies[-1]["content"])
        self.assertEqual(self.rest.ban_calls, [])

    def test_ban_works_when_antiban_disarmed(self):
        self.engine.settings.anti_ban = False
        self.engine.on_message(message(OWNER_ID, "+ban <@777777777777777777> spam"))
        self.assertEqual(self.rest.ban_calls[0][0], 777777777777777777)

    def test_keepbanned_add(self):
        self.engine.on_message(message(OWNER_ID, "+keepbanned add <@888888888888888888>"))
        self.assertIn(888888888888888888, self.engine.settings.keep_banned)

    def test_help_lists_codes(self):
        self.engine.on_message(message(5555, "+help"))
        body = self.rest.replies[-1]["content"]
        self.assertIn("Suspected spy", body)
        self.assertIn("+ping", body)


class AutomodTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_slur_is_a_warning(self):
        self.engine.on_message(message(4444, "you n1gga"))
        self.assertEqual(self.rest.timeouts, [])
        self.assertIn("Strike 1", self.rest.replies[-1]["content"])

    def test_second_slur_times_out(self):
        self.engine.on_message(message(4444, "you n1gga"))
        self.engine.on_message(message(4444, "n1gga again", message_id=2))
        self.assertEqual(self.rest.timeouts[0][0], 4444)
        self.assertIn("Strike 2", self.rest.replies[-1]["content"])

    def test_third_slur_asks_operators(self):
        for index in range(3):
            self.engine.on_message(message(4444, "n1gga", message_id=index + 1))
        self.assertIn(f"<@{LYNX_ID}>", self.rest.replies[-1]["content"])
        self.assertIn(f"<@{ARCEUS_ID}>", self.rest.replies[-1]["content"])
        self.assertIn("slur", self.engine.store.questions)

    def test_exempt_member_is_not_struck(self):
        self.engine.on_message(message(LYNX_ID, "n1gga"))
        self.assertEqual(self.rest.replies, [])

    def test_invite_is_deleted(self):
        self.engine.on_message(message(4444, "join discord.gg/abc"))
        self.assertEqual(self.rest.deleted[0][1], 1)

    def test_spam_timeout(self):
        for index in range(self.engine.settings.spam_limit):
            self.engine.on_message(message(4444, "spam", message_id=index + 1))
        self.assertTrue(self.rest.timeouts)

    def test_punish_requires_bot_mention(self):
        self.engine.on_message(message(LYNX_ID, "punish dyllan"))
        self.assertEqual(self.rest.timeouts, [])
        self.engine.on_message(message(LYNX_ID, f"<@{BOT_ID}> punish dyllan", message_id=2))
        self.assertEqual(self.rest.timeouts[0][0], DYLLAN_ID)

    def test_punish_from_non_operator_is_ignored(self):
        self.engine.on_message(message(4444, f"<@{BOT_ID}> punish dyllan"))
        self.assertEqual(self.rest.timeouts, [])

    def test_three_punishments_start_a_lock_vote(self):
        self.engine.settings.punish_strikes_to_lock = 2
        self.engine.on_message(message(LYNX_ID, f"<@{BOT_ID}> punish dyllan", message_id=1))
        self.engine.on_message(message(LYNX_ID, f"<@{BOT_ID}> punish dyllan", message_id=2))
        self.assertIn("lockvote", self.engine.store.questions)

    def test_automod_off_lets_slurs_through(self):
        self.engine.settings.moderation_enabled = False
        self.engine.on_message(message(4444, "n1gga"))
        self.assertEqual(self.rest.replies, [])


class AntiBanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sweep_lifts_bans_but_respects_keep_banned(self):
        self.engine.settings.keep_banned = {9001}
        self.rest.ban_rows = [
            {"user": {"id": "111", "username": "a"}},
            {"user": {"id": "9001", "username": "veil"}},
        ]
        lifted = self.engine.mod.anti_ban_sweep()
        self.assertEqual(lifted, [111])
        self.assertEqual(self.rest.unbans, [111])

    def test_keep_banned_is_reapplied(self):
        self.engine.settings.keep_banned = {9001}
        self.rest.ban_rows = []
        applied = self.engine.mod.enforce_keep_banned()
        self.assertEqual(applied, [9001])

    def test_event_ban_is_reversed(self):
        self.engine.on_ban_add({"user": {"id": "222"}})
        self.assertEqual(self.rest.unbans, [222])
        self.assertIn("Anti-ban reversed", self.rest.sent[-1]["content"])

    def test_known_ban_is_not_reversed(self):
        self.engine.store.known_bans = {222}
        self.engine.on_ban_add({"user": {"id": "222"}})
        self.assertEqual(self.rest.unbans, [])

    def test_antiban_off_leaves_bans_alone(self):
        self.engine.settings.anti_ban = False
        self.engine.on_ban_add({"user": {"id": "222"}})
        self.assertEqual(self.rest.unbans, [])

    def test_seed_known_bans(self):
        self.rest.ban_rows = [{"user": {"id": "333", "username": "c"}}]
        self.engine.mod.seed_known_bans()
        self.assertEqual(self.engine.store.known_bans, {333})


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_strip_keeps_eternal(self):
        self.rest.members[4444] = {
            "user": {"username": "t"}, "roles": [str(ROLE_ETERNAL), "1234"],
        }
        removed, skipped = self.engine.mod.strip_roles(4444)
        self.assertEqual(removed, ["1234"])
        self.assertEqual(skipped, ["Eternal"])

    def test_managed_role_is_skipped(self):
        self.engine.mod.roles[1234] = RoleInfo(1234, "bot-role", 1, True, 0)
        self.rest.members[4444] = {"user": {"username": "t"}, "roles": ["1234"]}
        removed, skipped = self.engine.mod.strip_roles(4444, keep=())
        self.assertEqual(removed, [])
        self.assertEqual(skipped, ["bot-role (above bot)"])

    def test_snapshot_then_restore(self):
        self.rest.members[4444] = {"user": {"username": "t"}, "roles": ["1234"]}
        self.engine.mod.snapshot(4444)
        self.assertEqual(self.engine.store.snapshots["4444"], [1234])
        added, _ = self.engine.mod.restore(4444)
        self.assertEqual(added, ["1234"])
        self.assertIn((4444, 1234), self.rest.role_added)


class TempOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, content, uid=LYNX_ID):
        self.engine.on_message({
            "id": "1", "channel_id": str(MAIN_CHAT_ID), "content": content,
            "author": {"id": str(uid), "username": "u", "bot": False},
            "member": {"roles": []},
        })
        return self.rest.replies[-1]["content"] if self.rest.replies else ""

    def test_lynx_can_grant_ten_minutes(self):
        out = self._run(f"+Temp Ownership <@{WATCH_ID}>")
        self.assertIn("temporary owner for 10 minutes", out)
        self.assertIn((WATCH_ID, ROLE_CO_OWNER), self.rest.role_added)
        self.assertTrue(self.engine.tempown.active(WATCH_ID))

    def test_lowercase_and_bare_mention_work(self):
        out = self._run(f"+temp ownership <@{WATCH_ID}> 5")
        self.assertIn("5 minutes", out)
        self.assertTrue(self.engine.tempown.active(WATCH_ID))

    def test_nobody_else_can_run_it(self):
        """The owner is an owner tier but still cannot lend ownership."""
        out = self._run(f"+Temp Ownership <@{WATCH_ID}>", uid=OWNER_ID)
        self.assertIn("Only Lynx", out)
        self.assertEqual(self.rest.role_added, [])

    def test_a_moderator_cannot_run_it(self):
        out = self._run(f"+Temp Ownership <@{WATCH_ID}>", uid=999111222)
        self.assertIn("Only Lynx", out)
        self.assertEqual(self.rest.role_added, [])

    def test_grant_confers_the_owner_tier(self):
        self.assertEqual(self.engine.tier_of(WATCH_ID, set()), "user")
        self._run(f"+Temp Ownership <@{WATCH_ID}>")
        self.assertEqual(self.engine.tier_of(WATCH_ID, set()), "owner")

    def test_second_grant_revokes_the_first(self):
        self._run(f"+Temp Ownership <@{WATCH_ID}>")
        self._run(f"+Temp Ownership <@{ARCEUS_ID}>")
        self.assertIn((WATCH_ID, ROLE_CO_OWNER), self.rest.role_removed)
        self.assertFalse(self.engine.tempown.active(WATCH_ID))
        self.assertTrue(self.engine.tempown.active(ARCEUS_ID))

    def test_expiry_removes_the_role(self):
        self._run(f"+Temp Ownership <@{WATCH_ID}>")
        self._expire()
        revoked = self.engine.tempown.sweep()
        self.assertIsNotNone(revoked)
        self.assertIn((WATCH_ID, ROLE_CO_OWNER), self.rest.role_removed)
        self.assertEqual(self.engine.tier_of(WATCH_ID, set()), "user")

    def test_sweep_does_nothing_before_the_deadline(self):
        self._run(f"+Temp Ownership <@{WATCH_ID}>")
        self.assertIsNone(self.engine.tempown.sweep())
        self.assertTrue(self.engine.tempown.active(WATCH_ID))

    def test_grant_survives_a_restart_with_its_deadline(self):
        self._run(f"+Temp Ownership <@{WATCH_ID}>")
        deadline = self.engine.tempown.grant.expires_at

        store = Store(Path(self.tmp.name) / "state.json")
        store.load()
        rest = FakeRest()
        engine = Engine(rest, store, Codebook())
        self.assertTrue(engine.tempown.active(WATCH_ID))
        self.assertAlmostEqual(engine.tempown.grant.expires_at, deadline, places=1)

    def _expire(self):
        """Push the stored deadline into the past, as time passing would."""
        grant = self.engine.tempown.grant
        grant.expires_at = time.time() - 1
        self.engine.tempown._save(grant)

    def test_expired_grant_is_not_active_after_a_restart(self):
        self._run(f"+Temp Ownership <@{WATCH_ID}>")
        self._expire()

        store = Store(Path(self.tmp.name) / "state.json")
        store.load()
        engine = Engine(FakeRest(), store, Codebook())
        self.assertFalse(engine.tempown.active(WATCH_ID))
        self.assertEqual(engine.tier_of(WATCH_ID, set()), "user")

    def test_end_takes_it_back(self):
        self._run(f"+Temp Ownership <@{WATCH_ID}>")
        out = self._run("+Temp Ownership end")
        self.assertIn("removed", out)
        self.assertFalse(self.engine.tempown.active(WATCH_ID))

    def test_status_reports_the_remaining_time(self):
        self._run(f"+Temp Ownership <@{WATCH_ID}>")
        out = self._run("+Temp Ownership status")
        self.assertIn("temporary ownership", out)
        self.assertIn("left", out)

    def test_cannot_grant_to_the_bot(self):
        out = self._run(f"+Temp Ownership <@{BOT_ID}>")
        self.assertIn("cannot own", out)
        self.assertEqual(self.rest.role_added, [])

    def test_discord_refusal_is_reported(self):
        self.rest.status = 403
        out = self._run(f"+Temp Ownership <@{WATCH_ID}>")
        self.assertIn("refused", out)
        self.assertFalse(self.engine.tempown.active(WATCH_ID))


class BankruptTests(unittest.TestCase):
    """`+bankrupt` strips everything and `+bankrupt recover` gives it back."""

    # Real Discord snowflakes are 15+ digits; user_id_from rejects anything
    # shorter, so these must be realistic.
    VICTIM = 555000111222333444
    PLAIN = 777000222333444555

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)
        self.rest.members[self.VICTIM] = {
            "user": {"id": str(self.VICTIM)}, "roles": [str(ROLE_ETERNAL), "1234"],
        }
        self.rest.members[self.PLAIN] = {"user": {"id": str(self.PLAIN)}, "roles": []}

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, content, uid=LYNX_ID, roles=None):
        self.engine.on_message({
            "id": "1", "channel_id": str(MAIN_CHAT_ID), "content": content,
            "author": {"id": str(uid), "username": "u", "bot": False},
            "member": {"roles": [str(r) for r in (roles or [])]},
        })
        return self.rest.replies[-1]["content"] if self.rest.replies else ""

    def _roles(self, uid=None):
        return set(self.rest.members[uid or self.VICTIM]["roles"])

    # -- the main action --------------------------------------------------
    def test_strips_every_manageable_role(self):
        out = self._run(f"+bankrupt <@{self.VICTIM}>")
        self.assertIn("Bankrupt", out)
        self.assertNotIn("1234", self._roles())
        self.assertIn((self.VICTIM, 1234), self.rest.role_removed)

    def test_keeps_the_base_member_role(self):
        """@Eternal is the guild's floor; stripping it would remove them entirely."""
        self._run(f"+bankrupt <@{self.VICTIM}>")
        self.assertIn(str(ROLE_ETERNAL), self._roles())

    def test_notifies_the_user_by_dm(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        self.assertEqual(len(self.rest.dms), 1)
        self.assertEqual(self.rest.dms[0]["user"], self.VICTIM)
        self.assertIn("removed", self.rest.dms[0]["content"].lower())

    def test_reports_when_the_dm_could_not_be_sent(self):
        self.rest.dm_open = False
        out = self._run(f"+bankrupt <@{self.VICTIM}>")
        self.assertIn("DMs are closed", out)
        self.assertEqual(self.rest.dms, [])

    def test_records_what_was_taken(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        record = self.engine.store.bankrupt[str(self.VICTIM)]
        self.assertEqual(record["roles"], [1234])
        self.assertEqual(record["by"], LYNX_ID)

    def test_every_tier_can_run_it(self):
        for uid, roles in ((LYNX_ID, []), (self.PLAIN, []), (1186091734137045043, [ROLE_MOD])):
            with self.subTest(tier=uid):
                self.rest.members[self.VICTIM]["roles"] = [str(ROLE_ETERNAL), "1234"]
                out = self._run(f"+bankrupt <@{self.VICTIM}>", uid=uid, roles=roles)
                self.assertIn("Bankrupt", out)

    # -- recovery ---------------------------------------------------------
    def test_recover_restores_the_exact_roles(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        out = self._run(f"+bankrupt recover <@{self.VICTIM}>")
        self.assertIn("Recovered", out)
        self.assertIn("1234", self._roles())

    def test_recover_clears_the_record(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        self._run(f"+bankrupt recover <@{self.VICTIM}>")
        self.assertNotIn(str(self.VICTIM), self.engine.store.bankrupt)

    def test_recover_twice_reports_nothing_on_record(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        self._run(f"+bankrupt recover <@{self.VICTIM}>")
        out = self._run(f"+bankrupt recover <@{self.VICTIM}>")
        self.assertIn("No bankruptcy on record", out)

    def test_a_moderator_can_recover(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        out = self._run(f"+bankrupt recover <@{self.VICTIM}>", uid=1186091734137045043, roles=[ROLE_MOD])
        self.assertIn("Recovered", out)

    def test_a_plain_member_cannot_recover(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        out = self._run(f"+bankrupt recover <@{self.VICTIM}>", uid=self.PLAIN)
        self.assertIn("Only a moderator or the owner", out)
        self.assertNotIn("1234", self._roles())

    def test_restore_keeps_working_as_an_alias(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        out = self._run(f"+bankrupt restore <@{self.VICTIM}>")
        self.assertIn("Recovered", out)

    def test_record_survives_a_restart(self):
        self._run(f"+bankrupt <@{self.VICTIM}>")
        store = Store(Path(self.tmp.name) / "state.json")
        store.load()
        self.assertIn(str(self.VICTIM), store.bankrupt)
        self.assertEqual(store.bankrupt[str(self.VICTIM)]["roles"], [1234])

    # -- guards -----------------------------------------------------------
    def test_cannot_bankrupt_the_owner(self):
        for uid in (OWNER_ID, LYNX_ID, ARCEUS_ID):
            with self.subTest(target=uid):
                out = self._run(f"+bankrupt <@{uid}>")
                self.assertIn("protected operator", out)

    def test_cannot_bankrupt_yourself(self):
        out = self._run(f"+bankrupt <@{self.PLAIN}>", uid=self.PLAIN)
        self.assertIn("cannot bankrupt yourself", out)

    def test_cannot_bankrupt_the_bot(self):
        out = self._run(f"+bankrupt <@{BOT_ID}>")
        self.assertIn("bankrupt myself", out)

    def test_a_member_cannot_bankrupt_staff(self):
        self.rest.members[1186091734137045043] = {
            "user": {"id": "1186091734137045043"}, "roles": [str(ROLE_MOD)],
        }
        out = self._run(f"+bankrupt <@1186091734137045043>", uid=self.PLAIN)
        self.assertIn("is staff", out)
        self.assertIn(str(ROLE_MOD), self.rest.members[1186091734137045043]["roles"])

    def test_an_owner_can_bankrupt_a_moderator(self):
        self.rest.members[1186091734137045043] = {
            "user": {"id": "1186091734137045043"}, "roles": [str(ROLE_ETERNAL), str(ROLE_MOD)],
        }
        out = self._run(f"+bankrupt <@1186091734137045043>")
        self.assertIn("Bankrupt", out)
        self.assertNotIn(str(ROLE_MOD), self.rest.members[1186091734137045043]["roles"])

    def test_missing_target_shows_usage(self):
        out = self._run("+bankrupt")
        self.assertIn("+bankrupt", out)

    def test_unknown_member_is_reported(self):
        out = self._run("+bankrupt <@999999999999999999>")
        self.assertIn("no roles I am allowed to remove", out)

    def test_a_failed_removal_is_not_recorded(self):
        """Only roles actually taken go into the record, so recovery is honest."""
        self.rest.status = 403
        out = self._run(f"+bankrupt <@{self.VICTIM}>")
        self.assertIn("no roles I am allowed to remove", out)
        self.assertNotIn(str(self.VICTIM), self.engine.store.bankrupt)


class AlertRoomTests(unittest.TestCase):
    """Code 8 opens a private room for exactly four people and says nothing in chat."""

    OUTSIDER = 888000111222333444

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)
        self.rest.role_rows.append(
            {"id": str(GUILD_ID), "name": "@everyone", "permissions": "0", "position": 0}
        )
        self.engine.ensure_ops()

    def tearDown(self):
        self.tmp.cleanup()

    def _room_id(self):
        return next(iter(self.engine.rooms))

    def _overwrites(self):
        for row in self.rest.created_channels:
            if str(row["name"]).startswith("alert-8"):
                return {int(o["id"]): o for o in row["overwrites"]}
        return {}

    # -- the four people --------------------------------------------------
    def test_room_is_visible_to_exactly_the_four_named_people(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        rows = self._overwrites()
        allowed = {OWNER_ID, ARCEUS_ID, LYNX_ID, SPY_ID, BOT_ID}
        for user_id in allowed:
            self.assertIn(user_id, rows, f"{user_id} must be allowed")
            self.assertEqual(rows[user_id]["type"], 1, "must be a MEMBER overwrite")
            self.assertEqual(rows[user_id]["deny"], "0")
        self.assertEqual(set(rows), allowed | {GUILD_ID})

    def test_everyone_is_denied(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertEqual(self._overwrites()[GUILD_ID]["deny"], str(1 << 10 | 1 << 11))

    def test_no_role_overwrite_is_used(self):
        """A role could be handed to someone and would silently widen the room."""
        self.engine.on_message(message(LYNX_ID, "code 8"))
        for target, row in self._overwrites().items():
            if target != GUILD_ID:
                self.assertEqual(row["type"], 1)

    def test_dyllan_and_moderators_are_not_in_the_room(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        rows = self._overwrites()
        self.assertNotIn(WATCH_ID, rows)

    def test_allows_only_the_four_plus_the_bot(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        room = self.engine.rooms[self._room_id()]
        for user_id in (OWNER_ID, ARCEUS_ID, LYNX_ID, SPY_ID):
            self.assertTrue(room.allows(user_id))
        self.assertFalse(room.allows(self.OUTSIDER))
        self.assertFalse(room.allows(WATCH_ID))

    # -- secrecy ----------------------------------------------------------
    def test_nothing_is_posted_in_open_chat(self):
        self.engine.on_message(message(LYNX_ID, "code 8", message_id=77))
        self.assertNotIn(MAIN_CHAT_ID, {row["channel"] for row in self.rest.sent})

    def test_the_trigger_message_is_deleted(self):
        self.engine.on_message(message(LYNX_ID, "code 8", message_id=77))
        self.assertIn((MAIN_CHAT_ID, 77), self.rest.deleted)

    def test_the_alert_carries_the_pings_inside_the_room(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        body = self.rest.sent[0]["content"]
        self.assertIn("CODE 8", body)
        self.assertIn(f"<@{OWNER_ID}>", body)
        self.assertIn(f"<@{ARCEUS_ID}>", body)

    def test_the_alert_pings_only_arceus_and_the_owner(self):
        """Spy sits in the room but is not pinged - the room is not a summon."""
        self.engine.on_message(message(LYNX_ID, "code 8"))
        users = self.rest.sent[0]["allowed_mentions"]["users"]
        self.assertEqual(set(users), {str(OWNER_ID), str(ARCEUS_ID), str(LYNX_ID)})
        self.assertNotIn(str(SPY_ID), users)

    def test_only_one_room_is_opened_per_alert(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.engine.on_message(message(ARCEUS_ID, "code 8"))
        self.assertEqual(len([r for r in self.rest.created_channels
                              if str(r["name"]).startswith("alert-8")]), 2)

    # -- persistence ------------------------------------------------------
    def test_the_room_is_recorded_in_settings(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertEqual(len(self.engine.settings.room_channels), 1)

    def test_the_room_survives_a_restart(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        room_id = self._room_id()
        store = Store(Path(self.tmp.name) / "state.json")
        store.load()
        self.assertIn(room_id, store.settings.room_channels.values())

    def test_a_deleted_room_is_dropped_from_the_record(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        room = self.engine.rooms[self._room_id()]
        self.rest.channel_rows_by_id.pop(room.channel_id, None)
        self.rest.channels_by_id = {}
        name = next(iter(self.engine.settings.room_channels))
        fresh = AlertRoom(self.rest, self.engine.store, CODE8_MEMBERS)
        self.assertIsNone(fresh.load(name))
        self.assertNotIn(name, self.engine.store.settings.room_channels)

    # -- intrusions -------------------------------------------------------
    def test_an_outsider_is_evicted_from_the_room(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        room_id = self._room_id()
        self.engine.on_message(message(self.OUTSIDER, "let me in", channel_id=room_id))
        self.assertIn((room_id, self.OUTSIDER), self.rest.overwrite_deletes)

    def test_an_outsider_message_is_not_relayed_to_the_room(self):
        """Their words appear only inside the intrusion alert, never as content."""
        self.engine.on_message(message(LYNX_ID, "code 8"))
        room_id = self._room_id()
        before = len(self.rest.sent)
        self.engine.on_message(message(self.OUTSIDER, "hello", channel_id=room_id))
        posted = self.rest.sent[before:]
        self.assertTrue(posted, "the operators must be told")
        for row in posted:
            self.assertIn("Unauthorised access", row["content"])

    def test_an_outsider_cannot_run_a_command_in_the_room(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        room_id = self._room_id()
        self.engine.on_message(message(self.OUTSIDER, "+purge 50", channel_id=room_id))
        self.assertFalse(any("Purged" in r["content"] for r in self.rest.sent))

    # -- the administrator hole -------------------------------------------
    def test_the_leak_audit_names_administrator_roles(self):
        """A channel deny cannot beat Administrator, so say so out loud."""
        self.rest.role_rows.append(
            {"id": "1570969297226834091", "name": "Administrator",
             "permissions": str(1 << 3), "position": 14}
        )
        self.engine.on_message(message(LYNX_ID, "code 8"))
        body = self.rest.sent[0]["content"]
        self.assertIn("not fully private", body)
        self.assertIn("Administrator", body)

    def test_a_clean_guild_gets_no_leak_warning(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertNotIn("not fully private", self.rest.sent[0]["content"])

    def test_the_bots_own_roles_are_not_reported_as_leakers(self):
        self.rest.role_rows.append(
            {"id": "1572012974913101856", "name": "Freehands",
             "permissions": str(1 << 3), "position": 22}
        )
        self.rest.members[BOT_ID] = {"user": {"id": str(BOT_ID)},
                                     "roles": ["1572012974913101856"]}
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertNotIn("Freehands`", self.rest.sent[0]["content"])

    # -- the other codes are untouched ------------------------------------
    def test_code_10_keeps_its_existing_routing(self):
        """Only code 8 is room-based. Code 10 stays in the ops channel."""
        self.engine.on_message(message(LYNX_ID, "code 10"))
        self.assertEqual(self.rest.sent[0]["channel"], self.engine.ops.channel_id)
        self.assertFalse(any(str(r["name"]).startswith("alert-10")
                             for r in self.rest.created_channels))


class DemoteTests(unittest.TestCase):
    """`+demote` strips everything, says why to the victim, and tells the owner."""

    VICTIM = 555000111222333444
    REASON = "bullying and cosigning"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)
        self.rest.members[self.VICTIM] = {
            "user": {"id": str(self.VICTIM), "username": "z_nyxx"},
            "nick": None,
            "roles": [str(ROLE_ETERNAL), str(ROLE_MOD), "1234"],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, content, uid=LYNX_ID):
        self.engine.on_message(message(uid, content))
        return self.rest.replies[-1]["content"] if self.rest.replies else ""

    def _roles(self):
        return set(self.rest.members[self.VICTIM]["roles"])

    # -- the strip --------------------------------------------------------
    def test_strips_every_role_including_the_floor(self):
        """Unlike +bankrupt, a demotion is a full demotion: no role survives."""
        self._run(f"+demote <@{self.VICTIM}> {self.REASON}")
        self.assertEqual(self._roles(), set())

    def test_records_the_removed_roles(self):
        self._run(f"+demote <@{self.VICTIM}> {self.REASON}")
        removed = {rid for uid, rid in self.rest.role_removed if uid == self.VICTIM}
        self.assertEqual(removed, {ROLE_ETERNAL, ROLE_MOD, 1234})

    def test_saves_a_snapshot_so_restore_can_undo_it(self):
        self._run(f"+demote <@{self.VICTIM}> {self.REASON}")
        snap = self.engine.store.snapshots.get(str(self.VICTIM))
        self.assertIsNotNone(snap)
        self.assertIn(ROLE_MOD, snap)

    # -- telling people ---------------------------------------------------
    def test_the_victim_is_told_the_reason(self):
        self._run(f"+demote <@{self.VICTIM}> {self.REASON}")
        dms = [d for d in self.rest.dms if d["user"] == self.VICTIM]
        self.assertEqual(len(dms), 1)
        self.assertIn(self.REASON, dms[0]["content"])
        self.assertIn("removed", dms[0]["content"].lower())

    def test_the_owner_is_pinged_with_the_reason(self):
        self._run(f"+demote <@{self.VICTIM}> {self.REASON}")
        posted = self.rest.sent[-1]["content"]
        self.assertIn(f"<@{OWNER_ID}>", posted)
        self.assertIn(self.REASON, posted)

    def test_the_owner_mention_is_actually_allowed(self):
        self._run(f"+demote <@{self.VICTIM}> {self.REASON}")
        mentions = self.rest.sent[-1]["allowed_mentions"]["users"]
        self.assertEqual(mentions, [str(OWNER_ID)])

    def test_the_owner_also_gets_a_dm(self):
        self._run(f"+demote <@{self.VICTIM}> {self.REASON}")
        dms = [d for d in self.rest.dms if d["user"] == OWNER_ID]
        self.assertEqual(len(dms), 1)
        self.assertIn(self.REASON, dms[0]["content"])

    def test_reports_when_the_victims_dms_are_closed(self):
        self.rest.dm_open = False
        self._run(f"+demote <@{self.VICTIM}> {self.REASON}")
        self.assertIn("DMs are closed", self.rest.sent[-1]["content"])

    # -- guards -----------------------------------------------------------
    def test_a_reason_is_required(self):
        out = self._run(f"+demote <@{self.VICTIM}>")
        self.assertIn("reason is required", out.lower())
        self.assertEqual(self.rest.role_removed, [])

    def test_protected_operators_cannot_be_demoted(self):
        self.rest.members[OWNER_ID] = {"user": {"id": str(OWNER_ID)}, "roles": ["1234"]}
        out = self._run(f"+demote <@{OWNER_ID}> {self.REASON}")
        self.assertIn("protected", out)
        self.assertEqual(self.rest.role_removed, [])

    def test_a_moderator_cannot_run_it(self):
        out = self._run(f"+demote <@{self.VICTIM}> {self.REASON}", uid=self.VICTIM)
        self.assertEqual(self.rest.role_removed, [])

    def test_a_plain_member_cannot_run_it(self):
        self.rest.members[777000222333444555] = {
            "user": {"id": "777000222333444555"}, "roles": [],
        }
        out = self._run(f"+demote <@{self.VICTIM}> {self.REASON}", uid=777000222333444555)
        self.assertEqual(self.rest.role_removed, [])

    def test_nobody_can_demote_the_bot(self):
        out = self._run(f"+demote <@{BOT_ID}> {self.REASON}")
        self.assertIn("not going to demote myself", out)


class WatchTargetTests(unittest.TestCase):
    """The watch follows z_nyxx, and punishing Dyllan is a separate thing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)
        self.engine.ensure_ops()

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_watch_target_is_z_nyxx(self):
        self.assertEqual(WATCH_ID, 1566512766066491642)

    def test_watch_logs_messages_from_z_nyxx(self):
        self.engine.arm_watch(True)
        self.engine.on_message(message(WATCH_ID, "hello there"))
        self.assertEqual(len(self.rest.sent), 1)
        self.assertIn(str(WATCH_ID), self.rest.sent[0]["content"])

    def test_watch_ignores_dyllan_now(self):
        self.engine.arm_watch(True)
        self.engine.on_message(message(DYLLAN_ID, "hello there"))
        self.assertEqual(self.rest.sent, [])

    def test_punish_still_targets_dyllan_not_the_watch_target(self):
        self.engine.on_message(message(LYNX_ID, f"<@{BOT_ID}> punish dyllan"))
        self.assertEqual(self.rest.timeouts[0][0], DYLLAN_ID)
        self.assertNotEqual(self.rest.timeouts[0][0], WATCH_ID)

    def test_the_command_is_named_watchtarget(self):
        self.assertIsNotNone(self.engine.registry.resolve("watchtarget"))

    def test_the_old_dyllan_name_still_works(self):
        self.assertIsNotNone(self.engine.registry.resolve("dyllan"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class OpsChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)
        self.rest.role_rows.append(
            {"id": str(GUILD_ID), "name": "@everyone", "permissions": "0", "position": 0}
        )
        self.cid = self.engine.ensure_ops()

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_the_three_members_are_allowed(self):
        """Access is exactly three member overwrites - no role is involved."""
        self.assertEqual(len(self.rest.created_channels), 1)
        rows = {int(o["id"]): o for o in self.rest.created_channels[0]["overwrites"]}
        self.assertEqual(rows[GUILD_ID]["deny"], str(1 << 10 | 1 << 11))
        allowed = {OWNER_ID, ARCEUS_ID, LYNX_ID, BOT_ID}
        for user_id in allowed:
            self.assertEqual(rows[user_id]["type"], 1, "must be a MEMBER overwrite")
            self.assertEqual(rows[user_id]["allow"],
                             str(1 << 10 | 1 << 11 | 1 << 16 | 1 << 15 | 1 << 6))
            self.assertEqual(rows[user_id]["deny"], "0")
        # Nothing else: no role overwrite, and Dyllan is not present.
        self.assertEqual(set(rows), allowed | {GUILD_ID})
        self.assertNotIn(WATCH_ID, rows)
        for row in rows.values():
            if int(row["id"]) != GUILD_ID:
                self.assertEqual(row["type"], 1, "no role overwrites at all")

    def test_no_access_role_is_created(self):
        self.assertEqual(self.rest.created_roles, [])
        self.assertEqual(self.rest.role_added, [])

    def test_ensure_reuses_an_existing_channel(self):
        first = self.engine.ensure_ops()
        second = self.engine.ensure_ops()
        self.assertEqual(first, second)
        self.assertEqual(len(self.rest.created_channels), 1)

    def test_lock_reasserts_every_overwrite(self):
        self.rest.overwrites.clear()
        self.engine.ops._lock()
        for user_id in (OWNER_ID, ARCEUS_ID, LYNX_ID, BOT_ID, GUILD_ID):
            self.assertIn((self.cid, user_id), self.rest.overwrites)

    def test_lock_strips_a_stray_grant(self):
        """A manual grant must not survive the next lock."""
        self.rest.put_overwrite(self.cid, 999888777, 1, str(1 << 10), "0")
        self.engine.ops._lock()
        rows = self.rest.channel_rows_by_id[self.cid]["permission_overwrites"]
        self.assertNotIn(999888777, {int(o["id"]) for o in rows})

    def test_operator_may_post_in_the_channel(self):
        self.engine.on_message({
            "id": "5", "channel_id": str(self.cid), "content": "code 8",
            "author": {"id": str(LYNX_ID), "username": "lynx", "bot": False},
            "member": {"roles": []},
        })
        # An operator raising a code there is not treated as an intruder.
        self.assertEqual(self.rest.overwrite_deletes, [])

    def test_intruder_is_evicted_and_reported(self):
        self.engine.on_message({
            "id": "6", "channel_id": str(self.cid), "content": "let me in",
            "author": {"id": "424242", "username": "snoop", "bot": False},
            "member": {"roles": []},
        })
        self.assertIn((self.cid, 424242), self.rest.overwrite_deletes)
        notice = [s for s in self.rest.sent if "Unauthorised access" in s["content"]]
        self.assertEqual(len(notice), 1)
        self.assertIn("424242", notice[0]["content"])
        self.assertIn("let me in", notice[0]["content"])
        self.assertEqual(self.rest.kicks, [])

    def test_intruder_cannot_run_commands(self):
        self.engine.on_message({
            "id": "7", "channel_id": str(self.cid), "content": "+takeall 1",
            "author": {"id": "424242", "username": "snoop", "bot": False},
            "member": {"roles": []},
        })
        self.assertEqual(self.rest.role_removed, [])

    def test_admin_intruder_is_not_reported_as_removed(self):
        """Deleting an overwrite answers 200 even when nothing was there.

        An intruder who holds Administrator can still read the channel after the
        delete, so the notice must say so instead of claiming success.
        """
        self.rest.role_rows.append(
            {"id": "8888", "name": "THE KING", "permissions": str(1 << 3), "position": 17}
        )
        self.rest.members[424242] = {"roles": ["8888"]}
        self.engine.on_message({
            "id": "8", "channel_id": str(self.cid), "content": "hi",
            "author": {"id": "424242", "username": "snoop", "bot": False},
            "member": {"roles": ["8888"]},
        })
        notice = [s for s in self.rest.sent if "Unauthorised access" in s["content"]][0]
        self.assertIn("FAILED", notice["content"])
        self.assertIn(424242, self.rest.kicks)

    def test_plain_intruder_is_removed_without_a_kick(self):
        self.engine.on_message({
            "id": "9", "channel_id": str(self.cid), "content": "hi",
            "author": {"id": "424242", "username": "snoop", "bot": False},
            "member": {"roles": []},
        })
        notice = [s for s in self.rest.sent if "Unauthorised access" in s["content"]][0]
        self.assertIn("**Access revoked** yes", notice["content"])
        self.assertEqual(self.rest.kicks, [])

    def test_can_view_denies_a_plain_member(self):
        self.rest.members[424242] = {"roles": []}
        self.assertFalse(self.engine.ops.can_view(424242))

    def test_can_view_allows_an_allow_listed_member(self):
        self.rest.members[LYNX_ID] = {"roles": []}
        self.assertTrue(self.engine.ops.can_view(LYNX_ID))

    def test_can_view_short_circuits_on_administrator(self):
        self.rest.role_rows.append(
            {"id": "8888", "name": "Admin", "permissions": str(1 << 3), "position": 5}
        )
        self.rest.members[424242] = {"roles": ["8888"]}
        self.assertTrue(self.engine.ops.can_view(424242))

    def test_sensitive_codes_route_to_the_private_channel(self):
        self.engine.on_message(message(LYNX_ID, "code 10", message_id=42))
        self.assertEqual(self.rest.sent[-1]["channel"], self.cid)
        self.assertIn("CODE 10", self.rest.sent[-1]["content"])

    def test_code_8_never_lands_in_open_chat(self):
        """The whole point of the room: the alert must not be visible in chat."""
        self.engine.on_message(message(LYNX_ID, "code 8"))
        targets = {row["channel"] for row in self.rest.sent}
        self.assertNotIn(MAIN_CHAT_ID, targets)

    def test_code_8_lands_in_a_private_room(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        room_id = self.engine.rooms and next(iter(self.engine.rooms))
        self.assertTrue(room_id)
        self.assertEqual(self.rest.sent[0]["channel"], room_id)
        self.assertIn("CODE 8", self.rest.sent[0]["content"])


class DyllanWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)
        self.cid = self.engine.ensure_ops()

    def tearDown(self):
        self.tmp.cleanup()

    def test_code_11_means_dyllan_is_back(self):
        hit = self.engine.book.sense("code 11")
        self.assertEqual(hit.code.number, 11)
        self.assertEqual(hit.code.title, "Dyllan's back")
        self.assertTrue(hit.code.arm_watch)

    def test_code_11_arms_the_watch_and_alerts_privately(self):
        self.engine.on_message(message(LYNX_ID, "code 11"))
        self.assertTrue(self.engine.settings.watch_armed)
        self.assertEqual(self.rest.sent[-1]["channel"], self.cid)
        self.assertTrue(any("Watch armed" in s["content"] for s in self.rest.sent))

    def test_phrase_also_raises_code_11(self):
        self.engine.on_message(message(LYNX_ID, "dyllan is back"))
        self.assertTrue(self.engine.settings.watch_armed)

    def test_watch_is_silent_until_armed(self):
        self.engine.on_message(message(WATCH_ID, "hello everyone"))
        self.assertEqual(self.rest.sent, [])

    def test_armed_watch_logs_every_message_to_the_private_channel(self):
        self.engine.arm_watch(True)
        self.engine.on_message(message(WATCH_ID, "hello everyone", message_id=70))
        watch = [s for s in self.rest.sent if "**Watch**" in s["content"]]
        self.assertEqual(len(watch), 1)
        self.assertEqual(watch[0]["channel"], self.cid)
        self.assertIn("hello everyone", watch[0]["content"])

    def test_armed_watch_flags_rule_breaks(self):
        self.engine.arm_watch(True)
        self.engine.on_message(message(WATCH_ID, "join discord.gg/abc"))
        watch = [s for s in self.rest.sent if "**Watch**" in s["content"]][0]
        self.assertIn("invite", watch["content"])

    def test_watch_ignores_everyone_else(self):
        self.engine.arm_watch(True)
        self.engine.on_message(message(LYNX_ID, "hello"))
        self.assertFalse(any("**Watch**" in s["content"] for s in self.rest.sent))

    def test_master_switch_disables_the_watch(self):
        self.engine.arm_watch(True)
        self.engine.settings.watch_enabled = False
        self.engine.on_message(message(WATCH_ID, "hello"))
        self.assertFalse(any("**Watch**" in s["content"] for s in self.rest.sent))

    def test_armed_state_survives_a_restart(self):
        self.engine.arm_watch(True)
        reloaded = Store(Path(self.tmp.name) / "state.json")
        reloaded.load()
        self.assertTrue(reloaded.settings.watch_armed)


class CodebookTests(unittest.TestCase):
    def test_all_twenty_codes_exist(self):
        book = Codebook()
        self.assertEqual(sorted(book.codes), list(range(1, 21)))

    def test_unknown_numbers_do_not_trigger(self):
        book = Codebook()
        self.assertIsNone(book.sense("code 99"))
        self.assertIsNone(book.sense("42"))

    def test_dyllan_watch_code_is_the_only_arming_code(self):
        book = Codebook()
        arming = [c.number for c in book.codes.values() if c.arm_watch]
        self.assertEqual(arming, [11])

    def test_json_overrides_keep_the_routing_flags(self):
        """A codes.json entry must not silently drop ops/arm_watch."""
        import json
        import tempfile

        payload = {"codes": [
            {"number": 11, "title": "Dyllan's back", "ops": True, "arm_watch": True},
            {"number": 8, "title": "Suspected spy", "ops": False},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "codes.json"
            path.write_text(json.dumps(payload))
            book = Codebook.load(path)
        self.assertTrue(book.codes[11].arm_watch)
        self.assertTrue(book.codes[11].ops)
        self.assertFalse(book.codes[8].ops)
        self.assertEqual(book.codes[11].title, "Dyllan's back")
