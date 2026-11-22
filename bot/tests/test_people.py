"""Who the dropdown lists, and what the labels say.

The list is the safety surface for loops: a member who should not be targetable
must either be absent or marked protected, and the label has to match the power
they really hold.
"""

from __future__ import annotations

import unittest

from freehands.config import (
    ARCEUS_ID,
    LYNX_ID,
    OWNER_ID,
    ROLE_ADMIN,
    ROLE_CO_OWNER,
    ROLE_MOD,
)
from freehands.people import avatar_url, can_target, people, tier_for


def member(uid, name="user", roles=(), bot=False, nick=None):
    return {
        "user": {"id": str(uid), "username": name, "bot": bot},
        "roles": [str(r) for r in roles],
        "nick": nick,
    }


class TierTest(unittest.TestCase):
    def test_lynx_is_named_as_the_owner_of_freehands(self):
        tier, label = tier_for(str(LYNX_ID), set())
        self.assertEqual(tier, "owner")
        self.assertIn("Freehands", label)

    def test_the_owner_and_arceus_are_owners(self):
        for uid in (OWNER_ID, ARCEUS_ID):
            self.assertEqual(tier_for(str(uid), set())[0], "owner")

    def test_operator_roles_resolve_to_their_tier(self):
        self.assertEqual(tier_for("9", {ROLE_CO_OWNER})[0], "co-owner")
        self.assertEqual(tier_for("9", {ROLE_ADMIN})[0], "admin")
        self.assertEqual(tier_for("9", {ROLE_MOD})[0], "mod")

    def test_a_plain_member_is_a_user(self):
        self.assertEqual(tier_for("9", set())[0], "user")


class PeopleListTest(unittest.TestCase):
    def test_a_plain_member_is_not_listed(self):
        # A dropdown of the whole guild is a directory, not a control panel.
        rows = people([member("9", "nobody")])
        self.assertEqual(rows, [])

    def test_bots_are_not_listed(self):
        rows = people([member(LYNX_ID, "lynxbot", bot=True)])
        self.assertEqual(rows, [])

    def test_lynx_is_listed_but_protected(self):
        rows = people([member(LYNX_ID, "lynx")])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].protected)
        self.assertIn("Freehands", rows[0].reason)

    def test_ordering_puts_the_strongest_first(self):
        rows = people([
            member("30", "mod", roles=[ROLE_MOD]),
            member(LYNX_ID, "lynx"),
            member("20", "admin", roles=[ROLE_ADMIN]),
        ])
        self.assertEqual([r.display for r in rows], ["lynx", "admin", "mod"])

    def test_a_nickname_is_shown_in_place_of_the_username(self):
        rows = people([member(LYNX_ID, "lynx", nick="The Boss")])
        self.assertEqual(rows[0].display, "The Boss")

    def test_the_same_member_twice_is_listed_once(self):
        rows = people([member(LYNX_ID, "lynx"), member(LYNX_ID, "lynx")])
        self.assertEqual(len(rows), 1)

    def test_the_payload_has_the_fields_the_app_reads(self):
        row = people([member(LYNX_ID, "lynx")])[0].to_json()
        for key in ("id", "name", "display", "tier", "label", "avatar",
                    "protected", "reason"):
            self.assertIn(key, row)


class TargetTest(unittest.TestCase):
    def test_lynx_cannot_be_targeted(self):
        ok, why = can_target(str(LYNX_ID))
        self.assertFalse(ok)
        self.assertTrue(why)

    def test_anyone_else_can(self):
        self.assertTrue(can_target("555")[0])


class AvatarTest(unittest.TestCase):
    def test_an_animated_hash_keeps_its_gif(self):
        self.assertIn(".gif", avatar_url("1", "a_abc"))

    def test_a_static_hash_is_a_png(self):
        self.assertIn(".png", avatar_url("1", "abc"))

    def test_a_missing_hash_falls_back_to_a_default(self):
        self.assertIn("embed/avatars", avatar_url("1"))

    def test_junk_does_not_raise(self):
        self.assertIn("embed/avatars", avatar_url("not-a-number"))


if __name__ == "__main__":
    unittest.main()
