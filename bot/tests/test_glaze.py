"""Glazing Lynx.

The joke only stays funny if it does not repeat, does not fire on a command,
and cannot trigger itself. Those are the tests that matter; the phrase list is
checked for the properties that keep it readable.
"""

from __future__ import annotations

import random
import unittest

from freehands.glaze import COOLDOWN, PHRASES, Glazer, mentions_lynx


class MentionTest(unittest.TestCase):
    def test_a_plain_mention_matches(self):
        self.assertTrue(mentions_lynx("hi lynx"))
        self.assertTrue(mentions_lynx("LYNX"))
        self.assertTrue(mentions_lynx("is @lynx here"))

    def test_a_longer_word_does_not_match(self):
        # "lynxifyy" is the creator's handle; it is not a mention of the name.
        self.assertFalse(mentions_lynx("lynxifyy pushed a commit"))
        self.assertFalse(mentions_lynx("lynxed"))
        self.assertFalse(mentions_lynx("the lynxes"))

    def test_empty_input_is_safe(self):
        self.assertFalse(mentions_lynx(""))
        self.assertFalse(mentions_lynx(None))  # type: ignore[arg-type]


class GateTest(unittest.TestCase):
    def test_a_bot_is_ignored(self):
        glazer = Glazer(clock=lambda: 1000)
        self.assertFalse(glazer.should_glaze("c", "lynx", author_is_bot=True))

    def test_a_command_is_ignored(self):
        glazer = Glazer(clock=lambda: 1000)
        self.assertFalse(glazer.should_glaze("c", "+ban lynx", is_command=True))

    def test_a_message_without_the_name_is_ignored(self):
        glazer = Glazer(clock=lambda: 1000)
        self.assertFalse(glazer.should_glaze("c", "hello everyone"))

    def test_the_cooldown_is_per_channel(self):
        now = [1000.0]
        glazer = Glazer(cooldown=45, clock=lambda: now[0])
        self.assertTrue(glazer.should_glaze("a", "lynx"))
        glazer.phrase("a")
        self.assertFalse(glazer.should_glaze("a", "lynx again"))
        self.assertTrue(glazer.should_glaze("b", "lynx"), "another channel is not cooling")
        now[0] += COOLDOWN
        self.assertTrue(glazer.should_glaze("a", "lynx"), "the cooldown expired")

    def test_the_cooldown_blocks_a_burst(self):
        glazer = Glazer(cooldown=45, clock=lambda: 1000)
        glazer.phrase("c")
        for _ in range(5):
            self.assertFalse(glazer.should_glaze("c", "lynx"))


class PhraseTest(unittest.TestCase):
    def test_the_same_line_is_not_repeated_back_to_back(self):
        glazer = Glazer(clock=lambda: 1000, rng=random.Random(7))
        previous = glazer.phrase("c")
        for _ in range(30):
            current = glazer.phrase("c")
            self.assertNotEqual(current, previous)
            previous = current

    def test_every_phrase_mentions_lynx(self):
        for phrase in PHRASES:
            self.assertTrue(mentions_lynx(phrase), f"no mention in: {phrase}")

    def test_there_are_at_least_twenty(self):
        self.assertGreaterEqual(len(PHRASES), 20)

    def test_phrases_are_unique(self):
        self.assertEqual(len(PHRASES), len(set(PHRASES)))

    def test_phrases_stay_short(self):
        # These land mid-conversation, so a paragraph would read as spam.
        for phrase in PHRASES:
            self.assertLessEqual(len(phrase), 120, phrase)

    def test_phrase_records_the_time_for_the_cooldown(self):
        now = [1000.0]
        glazer = Glazer(cooldown=45, clock=lambda: now[0])
        glazer.phrase("c")
        self.assertFalse(glazer.should_glaze("c", "lynx"))
        now[0] += 1
        self.assertFalse(glazer.should_glaze("c", "lynx"))


if __name__ == "__main__":
    unittest.main()
