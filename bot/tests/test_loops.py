"""Loop ban / kick.

A loop repeats a destructive action on a timer, so the properties that matter
are the ones that stop it: it always ends, it never targets a protected member,
and it can always be stopped. The happy path is tested too, but it is the
brakes that would cost a server if they failed.
"""

from __future__ import annotations

import threading
import time
import unittest

from freehands.config import LYNX_ID, OWNER_ID
from freehands.loops import (
    IMMUNE,
    KIND_BAN,
    KIND_KICK,
    MAX_PASSES,
    MIN_INTERVAL,
    Loops,
    is_immune,
)


class FakeRest:
    """Records what a loop asked Discord to do."""

    def __init__(self, status: int = 204) -> None:
        self.calls: list[tuple] = []
        self.dms: list[tuple[int, str]] = []
        self.status = status

    def ban(self, guild_id, user_id, reason=None, delete_seconds=0):
        self.calls.append(("ban", user_id, reason, delete_seconds))
        return self.status

    def kick(self, guild_id, user_id, reason=None):
        self.calls.append(("kick", user_id, reason))
        return self.status

    def dm(self, user_id, text):
        self.dms.append((user_id, text))
        return True


def wait_until(predicate, timeout: float = 3.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class ImmuneTest(unittest.TestCase):
    def test_owner_and_lynx_are_protected(self):
        self.assertIn(OWNER_ID, IMMUNE)
        self.assertIn(LYNX_ID, IMMUNE)

    def test_is_immune_accepts_the_string_form(self):
        # Ids arrive from JSON and from the console as text, so the check has
        # to work on both forms or it silently protects nobody.
        self.assertTrue(is_immune(str(LYNX_ID)))
        self.assertTrue(is_immune(OWNER_ID))
        self.assertFalse(is_immune("123456789"))

    def test_is_immune_rejects_junk_without_raising(self):
        for junk in ("", "abc", None, "<@123>"):
            self.assertFalse(is_immune(junk))

    def test_a_loop_cannot_be_aimed_at_a_protected_member(self):
        loops = Loops(FakeRest())
        for who in (OWNER_ID, LYNX_ID):
            with self.assertRaises(ValueError):
                loops.arm(KIND_BAN, str(who), "x", 60, 2, "1")
        self.assertEqual(loops.listing(), [])


class ArmValidationTest(unittest.TestCase):
    def test_kind_must_be_ban_or_kick(self):
        loops = Loops(FakeRest())
        for kind in ("", "mute", "BANANA"):
            with self.assertRaises(ValueError):
                loops.arm(kind, "555", "x", 60, 1, "1")

    def test_target_must_be_a_user_id(self):
        loops = Loops(FakeRest())
        for target in ("", "everyone", "@here", "abc"):
            with self.assertRaises(ValueError):
                loops.arm(KIND_BAN, target, "x", 60, 1, "1")

    def test_interval_floor_stops_a_flood(self):
        loops = Loops(FakeRest())
        with self.assertRaises(ValueError):
            loops.arm(KIND_BAN, "555", "x", MIN_INTERVAL - 1, 1, "1")

    def test_interval_ceiling(self):
        loops = Loops(FakeRest())
        with self.assertRaises(ValueError):
            loops.arm(KIND_BAN, "555", "x", 7 * 3600, 1, "1")

    def test_pass_count_is_bounded(self):
        loops = Loops(FakeRest())
        with self.assertRaises(ValueError):
            loops.arm(KIND_BAN, "555", "x", 60, 0, "1")
        with self.assertRaises(ValueError):
            loops.arm(KIND_BAN, "555", "x", 60, MAX_PASSES + 1, "1")

    def test_one_loop_per_target_and_kind(self):
        rest = FakeRest()
        loops = Loops(rest)
        loops.arm(KIND_BAN, "555", "x", 600, 5, "1")
        with self.assertRaises(ValueError):
            loops.arm(KIND_BAN, "555", "x", 600, 5, "1")
        # A different kind on the same target is a separate loop.
        loops.arm(KIND_KICK, "555", "x", 600, 5, "1")
        self.assertEqual(len(loops.listing()), 2)


class RunTest(unittest.TestCase):
    def test_first_pass_fires_immediately(self):
        rest = FakeRest()
        loops = Loops(rest)
        loop = loops.arm(KIND_BAN, "555", "spam", 60, 2, "1")
        self.assertTrue(wait_until(lambda: loop.fired >= 1))
        self.assertEqual(rest.calls[0][0], "ban")
        self.assertEqual(rest.calls[0][1], 555)
        loops.stop_all()

    def test_ban_deletes_no_messages(self):
        # delete_seconds must be 0, or every pass erases a day of history.
        rest = FakeRest()
        loops = Loops(rest)
        loop = loops.arm(KIND_BAN, "555", "spam", 60, 1, "1")
        self.assertTrue(wait_until(lambda: loop.fired >= 1))
        self.assertEqual(rest.calls[0][3], 0)

    def test_a_loop_ends_by_itself(self):
        rest = FakeRest()
        loops = Loops(rest)
        loop = loops.arm(KIND_KICK, "555", "x", MIN_INTERVAL, 1, "1")
        self.assertTrue(wait_until(lambda: loop.stopped == "finished"))
        self.assertFalse(loop.running)

    def test_stop_takes_effect_promptly(self):
        rest = FakeRest()
        loops = Loops(rest)
        # A long interval: without an interruptible wait, this test would hang
        # for a minute and a stop would be useless in practice.
        loop = loops.arm(KIND_BAN, "555", "x", 600, 50, "1")
        self.assertTrue(wait_until(lambda: loop.fired >= 1))
        self.assertTrue(loops.stop(loop.id))
        self.assertTrue(wait_until(lambda: not loop.running))

    def test_stopping_an_unknown_loop_is_false(self):
        self.assertFalse(Loops(FakeRest()).stop("L999"))

    def test_stop_all_reports_a_count(self):
        loops = Loops(FakeRest())
        loops.arm(KIND_BAN, "555", "x", 600, 10, "1")
        loops.arm(KIND_BAN, "666", "x", 600, 10, "1")
        self.assertEqual(loops.stop_all(), 2)

    def test_a_rest_failure_is_recorded_not_raised(self):
        loops = Loops(FakeRest(status=500))
        loop = loops.arm(KIND_BAN, "555", "x", 600, 1, "1")
        self.assertTrue(wait_until(lambda: loop.fired >= 1))
        self.assertIn("500", loop.last_error)
        loops.stop_all()


class NotifyTest(unittest.TestCase):
    def test_dm_is_sent_once_before_the_first_pass(self):
        rest = FakeRest()
        loops = Loops(rest)
        loop = loops.arm(KIND_BAN, "555", "spam", 600, 3, "1", notify=True)
        self.assertTrue(wait_until(lambda: loop.dm_sent))
        self.assertEqual(len(rest.dms), 1)
        self.assertIn("banned", rest.dms[0][1])
        self.assertIn("spam", rest.dms[0][1])
        loops.stop_all()

    def test_no_dm_when_not_asked(self):
        rest = FakeRest()
        loops = Loops(rest)
        loop = loops.arm(KIND_BAN, "555", "x", 600, 1, "1")
        self.assertTrue(wait_until(lambda: loop.fired >= 1))
        self.assertEqual(rest.dms, [])
        self.assertFalse(loop.dm_sent)
        loops.stop_all()


class ListingTest(unittest.TestCase):
    def test_listing_carries_the_fields_the_app_reads(self):
        loops = Loops(FakeRest())
        loop = loops.arm(KIND_BAN, "555", "spam", 600, 4, "42")
        row = loops.listing()[0]
        for key in ("id", "kind", "target", "reason", "interval", "passes",
                    "fired", "armed_by", "running", "stopped", "last_error"):
            self.assertIn(key, row)
        self.assertEqual(row["armed_by"], "42")
        self.assertEqual(row["target"], "555")
        self.assertEqual(loop.remaining, 3)
        loops.stop_all()


if __name__ == "__main__":
    unittest.main()
