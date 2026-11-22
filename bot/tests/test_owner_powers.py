"""Owner powers.

The single property that matters most: only Lynx may read or flip a switch.
Everything else here is about the switches behaving predictably, because a
destructive toggle that fails halfway is worse than one that refuses.
"""

from __future__ import annotations

import unittest

from freehands.config import ARCEUS_ID, LYNX_ID, OWNER_ID
from freehands.owner_powers import (
    DESTRUCTIVE,
    POWERS,
    POWER_KEYS,
    OwnerPowers,
)


class FakeEngine:
    """Counts the effects the powers ask for, without touching Discord."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def lock_all_channels(self, on):
        self.calls.append(f"lock:{on}")
        return "locked 3/3 channels"

    def slow_all_channels(self, seconds):
        self.calls.append(f"slow:{seconds}")
        return f"slowmode {seconds}s"

    def delete_all_invites(self):
        self.calls.append("invites")
        return "deleted 2 invites"

    def rainbow_role(self, on):
        self.calls.append(f"rainbow:{on}")
        return "rainbow running" if on else "rainbow stopped"

    def mute_everyone(self, seconds=60):
        self.calls.append(f"mute:{seconds}")
        return "muted everyone"

    def strip_everyone(self):
        self.calls.append("strip")
        return "stripped 5 members"

    def purge_bots(self):
        self.calls.append("purge")
        return "kicked 1 bots"


class GateTest(unittest.TestCase):
    def test_only_lynx_may_read_the_panel(self):
        powers = OwnerPowers(FakeEngine())
        self.assertTrue(powers.panel(str(LYNX_ID))["ok"])
        for other in (str(OWNER_ID), str(ARCEUS_ID), "", "123"):
            payload = powers.panel(other)
            self.assertFalse(payload["ok"], f"{other} must not read the panel")
            self.assertIn("Lynx", payload["error"])

    def test_only_lynx_may_flip_a_switch(self):
        engine = FakeEngine()
        powers = OwnerPowers(engine)
        for other in (str(OWNER_ID), "", "123"):
            result = powers.set(other, "lock_everything", True)
            self.assertFalse(result["ok"])
        self.assertEqual(engine.calls, [], "a refused call must do nothing")

    def test_a_refused_call_does_not_change_state(self):
        powers = OwnerPowers(FakeEngine())
        powers.set(str(OWNER_ID), "ghost_mode", True)
        self.assertFalse(powers.is_on("ghost_mode"))

    def test_identity_is_compared_as_text(self):
        # The id arrives as a string from the device token, and as an int from
        # the command layer. Both have to open the same door.
        self.assertTrue(OwnerPowers.allowed(str(LYNX_ID)))
        self.assertTrue(OwnerPowers.allowed(LYNX_ID))
        self.assertFalse(OwnerPowers.allowed(str(OWNER_ID)))


class SwitchTest(unittest.TestCase):
    def test_everything_starts_off(self):
        powers = OwnerPowers(FakeEngine())
        for power in POWERS:
            self.assertFalse(powers.is_on(power.key), f"{power.key} must default off")

    def test_an_unknown_key_is_refused(self):
        result = OwnerPowers(FakeEngine()).set(str(LYNX_ID), "not_a_power", True)
        self.assertFalse(result["ok"])

    def test_flipping_on_and_off_updates_state(self):
        powers = OwnerPowers(FakeEngine())
        powers.set(str(LYNX_ID), "ghost_mode", True)
        self.assertTrue(powers.is_on("ghost_mode"))
        powers.set(str(LYNX_ID), "ghost_mode", False)
        self.assertFalse(powers.is_on("ghost_mode"))

    def test_a_confirm_switch_needs_the_word(self):
        engine = FakeEngine()
        powers = OwnerPowers(engine)
        refused = powers.set(str(LYNX_ID), "strip_all", True)
        self.assertFalse(refused["ok"])
        self.assertEqual(engine.calls, [])
        ok = powers.set(str(LYNX_ID), "strip_all", True, confirm="strip_all")
        self.assertTrue(ok["ok"])
        self.assertEqual(engine.calls, ["strip"])

    def test_confirm_is_case_insensitive(self):
        powers = OwnerPowers(FakeEngine())
        self.assertTrue(powers.set(str(LYNX_ID), "purge_bots", True, confirm="PURGE_BOTS")["ok"])

    def test_turning_a_confirm_switch_off_needs_no_token(self):
        powers = OwnerPowers(FakeEngine())
        powers.set(str(LYNX_ID), "strip_all", True, confirm="strip_all")
        self.assertTrue(powers.set(str(LYNX_ID), "strip_all", False)["ok"])

    def test_effects_fire_for_the_wired_switches(self):
        engine = FakeEngine()
        powers = OwnerPowers(engine)
        powers.set(str(LYNX_ID), "lock_everything", True)
        powers.set(str(LYNX_ID), "slow_everything", True)
        powers.set(str(LYNX_ID), "nuke_invites", True)
        powers.set(str(LYNX_ID), "rainbow", True)
        powers.set(str(LYNX_ID), "mute_all", True)
        self.assertIn("lock:True", engine.calls)
        self.assertIn("slow:15", engine.calls)
        self.assertIn("invites", engine.calls)
        self.assertIn("rainbow:True", engine.calls)
        self.assertIn("mute:60", engine.calls)

    def test_a_troll_switch_needs_no_effect_and_still_sets(self):
        engine = FakeEngine()
        powers = OwnerPowers(engine)
        result = powers.set(str(LYNX_ID), "ghost_mode", True)
        self.assertTrue(result["ok"])
        self.assertEqual(engine.calls, [])
        self.assertTrue(powers.is_on("ghost_mode"))

    def test_a_failing_effect_is_reported_not_raised(self):
        class Broken(FakeEngine):
            def lock_all_channels(self, on):
                raise RuntimeError("boom")

        powers = OwnerPowers(Broken())
        result = powers.set(str(LYNX_ID), "lock_everything", True)
        self.assertTrue(result["ok"], "the switch is still set")
        self.assertIn("boom", result["detail"])
        self.assertTrue(powers.is_on("lock_everything"))


class RegistryTest(unittest.TestCase):
    def test_every_power_has_the_fields_the_panel_needs(self):
        for power in POWERS:
            self.assertTrue(power.key)
            self.assertTrue(power.name)
            self.assertTrue(power.blurb)
            self.assertIn(power.kind, (DESTRUCTIVE, "disruptive", "troll"))

    def test_keys_are_unique(self):
        keys = [p.key for p in POWERS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_there_are_sixteen_powers(self):
        self.assertEqual(len(POWERS), 16)
        self.assertEqual(len(POWER_KEYS), 16)

    def test_the_irreversible_ones_require_a_confirm(self):
        by_key = {p.key: p for p in POWERS}
        self.assertTrue(by_key["strip_all"].confirm)
        self.assertTrue(by_key["purge_bots"].confirm)

    def test_the_panel_payload_matches_the_registry(self):
        payload = OwnerPowers(FakeEngine()).panel(str(LYNX_ID))
        self.assertEqual(len(payload["powers"]), len(POWERS))
        self.assertEqual(
            [p["key"] for p in payload["powers"]],
            [p.key for p in POWERS],
        )


if __name__ == "__main__":
    unittest.main()
