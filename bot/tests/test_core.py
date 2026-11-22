"""Unit tests for the pure logic: codes, parsing, text rules, vault, store."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from freehands import text
from freehands.codebook import DEFAULT_CODES, Codebook, render_alert
from freehands.commands import Registry, Spec, parse, user_id_from
from freehands.config import Settings
from freehands.store import Store
from freehands.vault import MissingToken, SALT, load_token, mask, unmask


class CodeSenseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.book = Codebook()

    def test_number_form(self):
        hit = self.book.sense("code 8")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.code.number, 8)
        self.assertEqual(hit.code.title, "Suspected spy")

    def test_number_with_separator_and_case(self):
        for probe in ("Code 10", "CODE-10", "code: 10", "code #10", "code10"):
            hit = self.book.sense(probe)
            self.assertIsNotNone(hit, probe)
            self.assertEqual(hit.code.number, 10, probe)

    def test_word_and_roman(self):
        self.assertEqual(self.book.sense("code eight").code.number, 8)
        self.assertEqual(self.book.sense("code VIII").code.number, 8)
        self.assertEqual(self.book.sense("code ten").code.number, 10)

    def test_bare_number_is_not_a_code(self):
        for probe in ("8", "i have 8 apples", "the 8 ball", "channel 10"):
            self.assertIsNone(self.book.sense(probe), probe)

    def test_obfuscated_spellings_are_still_sensed(self):
        """People type in a hurry, and a spy may try to dodge the filter."""
        for probe in ("c0de 8", "cod3 8", "c0d3 8", "kode 8",
                      "c o d e 8", "c.o.d.e 10", "c0de 10"):
            hit = self.book.sense(probe)
            self.assertIsNotNone(hit, probe)
            self.assertIn(hit.code.number, (8, 10), probe)

    def test_leet_folding_does_not_corrupt_the_number(self):
        """`code 10` must not become `code io` when digits are folded."""
        self.assertEqual(self.book.sense("c0de 10").code.number, 10)

    def test_words_that_merely_contain_code_stay_quiet(self):
        for probe in ("decode 8 bytes", "barcode 8", "enc0de 8 bytes",
                      "this code 8s broken", "the code is fine"):
            self.assertIsNone(self.book.sense(probe), probe)

    def test_sensing_a_quiet_message_is_cheap(self):
        """Every message is scanned, so the no-hit path must stay fast.

        The old implementation compiled 48 alias regexes per message; a budget
        of 60 us catches a return to that without being flaky on slow CI.
        """
        import timeit
        seconds = timeit.timeit(
            lambda: self.book.sense("ordinary chatter about nothing at all"),
            number=2000,
        )
        self.assertLess(seconds / 2000 * 1e6, 60.0)

    def test_phrase_alias(self):
        hit = self.book.sense("guys i think there's a spy")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.code.number, 8)

    def test_alias_requires_word_boundary(self):
        self.assertIsNone(self.book.sense("this is spying on the neighbours"))

    def test_unknown_number_ignored(self):
        self.assertIsNone(self.book.sense("code 99"))

    def test_code_8_pings_owner_and_arceus_with_eyes(self):
        code = self.book.get(8)
        self.assertTrue(code.ping_owner)
        self.assertTrue(code.ping_arceus)
        self.assertEqual(code.emoji, "\N{EYES}")

    def test_code_10_goes_dark(self):
        code = self.book.get(10)
        self.assertTrue(code.silence)
        self.assertEqual(code.severity, "critical")

    def test_every_default_code_has_a_meaning(self):
        for number, code in DEFAULT_CODES.items():
            self.assertTrue(code.meaning, number)
            self.assertTrue(code.response, number)
            self.assertIn(code.severity, ("low", "medium", "high", "critical"))

    def test_alert_renders_mentions(self):
        hit = self.book.sense("code 8")
        body = render_alert(hit, 111, "tester", 222, 333, [])
        self.assertIn("<@222>", body)
        self.assertIn("<@333>", body)
        self.assertIn("SUSPECTED SPY", body)
        self.assertIn("\N{EYES}", body)

    def test_json_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "codes.json"
            path.write_text(json.dumps({
                "codes": [{"number": 8, "title": "Custom spy", "response": "custom"}]
            }), encoding="utf-8")
            book = Codebook.load(path)
            hit = book.sense("code 8")
            self.assertEqual(hit.code.title, "Custom spy")
            self.assertEqual(hit.code.response, "custom")
            # untouched fields fall back to the defaults
            self.assertTrue(hit.code.ping_owner)


class CommandParseTests(unittest.TestCase):
    def test_parse_basic(self):
        cmd = parse("+mute <@123> 10m spam")
        self.assertEqual(cmd.name, "mute")
        self.assertEqual(cmd.args, ["<@123>", "10m", "spam"])

    def test_parse_rejects_plain_text(self):
        self.assertIsNone(parse("hello there"))
        self.assertIsNone(parse("+"))

    def test_parse_lowercases_name_but_not_args(self):
        cmd = parse("+Say Hello World")
        self.assertEqual(cmd.name, "say")
        self.assertEqual(cmd.text, "Hello World")

    def test_registry_alias(self):
        reg = Registry()
        reg.add(Spec("keepbanned", lambda *a: None, aliases=("kb",)))
        self.assertEqual(reg.resolve("kb").name, "keepbanned")

    def test_suggestion(self):
        reg = Registry()
        reg.add(Spec("antiban", lambda *a: None))
        self.assertEqual(reg.suggest("antibna"), "antiban")

    def test_tier_filtering(self):
        reg = Registry()
        reg.add(Spec("help", lambda *a: None, "user"))
        reg.add(Spec("ban", lambda *a: None, "owner"))
        # A normal user only sees user-tier commands; an owner sees everything,
        # with the most privileged group listed first.
        self.assertEqual([s.name for s in reg.by_tier("user")], ["help"])
        self.assertEqual([s.name for s in reg.by_tier("owner")], ["ban", "help"])

    def test_user_id_extraction(self):
        self.assertEqual(user_id_from("<@123456789012345678>"), 123456789012345678)
        self.assertEqual(user_id_from("<@!123456789012345678>"), 123456789012345678)
        self.assertEqual(user_id_from("123456789012345678"), 123456789012345678)
        self.assertIsNone(user_id_from("nope"))
        self.assertIsNone(user_id_from("1234"))


class TextRuleTests(unittest.TestCase):
    def test_slur_detection(self):
        self.assertTrue(text.has_slur("you n1gga"))
        self.assertTrue(text.has_slur("NIQQER"))
        self.assertFalse(text.has_slur("night"))
        self.assertFalse(text.has_slur("nigh"))

    def test_invite_detection(self):
        self.assertTrue(text.has_invite("join discord.gg/abc123"))
        self.assertFalse(text.has_invite("discord is fun"))

    def test_punish_request_needs_target(self):
        self.assertTrue(text.is_punish_request("punish dyllan"))
        self.assertTrue(text.is_punish_request("please punish mysterious stranger"))
        self.assertFalse(text.is_punish_request("punish him"))
        self.assertFalse(text.is_punish_request("dyllan is here"))

    def test_duration_parsing(self):
        self.assertEqual(text.parse_duration("10m"), 600)
        self.assertEqual(text.parse_duration("2h"), 7200)
        self.assertEqual(text.parse_duration("4d"), 345600)
        self.assertEqual(text.parse_duration("90"), 90)
        self.assertIsNone(text.parse_duration("soon"))

    def test_human_duration(self):
        self.assertEqual(text.human_duration(600), "10m")
        self.assertEqual(text.human_duration(7200), "2h")
        self.assertEqual(text.human_duration(90), "90s")

    def test_caps_flood(self):
        self.assertTrue(text.is_caps_flood("WHY IS EVERYTHING SHOUTING RIGHT NOW"))
        self.assertFalse(text.is_caps_flood("this is a normal sentence"))

    def test_spam_tracker_window(self):
        tracker = text.SpamTracker(limit=3, window=10)
        self.assertEqual(tracker.hit(1, now=0), 1)
        self.assertEqual(tracker.hit(1, now=1), 2)
        self.assertEqual(tracker.hit(1, now=2), 3)
        self.assertEqual(tracker.hit(1, now=100), 1)

    def test_raid_tracker(self):
        tracker = text.RaidTracker(joins=3, window=10)
        self.assertFalse(tracker.hit(now=0))
        self.assertFalse(tracker.hit(now=1))
        self.assertTrue(tracker.hit(now=2))
        self.assertFalse(tracker.hit(now=100))


class VaultTests(unittest.TestCase):
    def test_mask_round_trip(self):
        token = "OTk5OTk5OTk5OTk5OTk5OTk5.ABCDEF.synthetic_value_for_tests"
        fragments = mask(token)
        self.assertEqual(unmask(tuple(fragments), SALT), token)

    def test_no_embedded_token_is_shipped(self):
        """A committed blob is a published credential, however it is encoded."""
        with self.assertRaises(MissingToken):
            unmask()

    def test_load_token_prefers_the_environment(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"FH_TOKEN": "from-env"}, clear=False):
            self.assertEqual(load_token(), "from-env")

    def test_load_token_reads_the_gitignored_file(self):
        import os
        from unittest import mock

        from freehands import vault

        tmp = Path(tempfile.mkdtemp()) / ".token"
        tmp.write_text("from-file\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(vault, "_candidates", return_value=[tmp]):
                self.assertEqual(load_token(), "from-file")

    def test_load_token_refuses_to_invent_one(self):
        import os
        from unittest import mock

        from freehands import vault

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(vault, "_candidates", return_value=[]):
                with self.assertRaises(MissingToken):
                    load_token()

    def test_no_plaintext_token_in_source_tree(self):
        """Nothing under freehands/ should look like a Discord bot token."""
        import re

        root = Path(__file__).resolve().parent.parent / "freehands"
        pattern = re.compile(r"[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,40}")
        for path in root.glob("*.py"):
            self.assertIsNone(
                pattern.search(path.read_text(encoding="utf-8")), path.name
            )


class StoreTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = Store(path)
            store.settings.anti_ban = False
            store.settings.keep_banned = {42}
            store.strike(7, "slur")
            store.strike(7, "slur")
            store.snapshots["7"] = [1, 2]
            store.add_incident({"code": 8})
            store.save(force=True)

            other = Store(path)
            other.load()
            self.assertFalse(other.settings.anti_ban)
            self.assertEqual(other.settings.keep_banned, {42})
            self.assertEqual(other.get_strikes(7, "slur"), 2)
            self.assertEqual(other.snapshots["7"], [1, 2])
            self.assertEqual(other.incidents[0]["code"], 8)

    def test_corrupt_state_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            store = Store(path)
            store.load()
            self.assertTrue(store.settings.anti_ban)

    def test_settings_from_unknown_keys(self):
        settings = Settings.from_json({"anti_ban": False, "nonsense": 1})
        self.assertFalse(settings.anti_ban)


if __name__ == "__main__":
    unittest.main(verbosity=2)
