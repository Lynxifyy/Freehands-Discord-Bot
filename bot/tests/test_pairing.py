"""Pairing is the only way a phone gets a credential, so its rules are tested.

The properties that matter: a code is single-use, a code expires, a token is
never stored in recoverable form, and a revoked device stops working.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from freehands.pairing import CODE_LENGTH, Device, Pairing, normalise
from freehands.store import Store


def tmp_store() -> Store:
    """A Store backed by a throwaway file, with `load` already called."""
    tmp = tempfile.mkdtemp()
    store = Store(Path(tmp) / "state.json")
    store.load()
    return store


class CodeTest(unittest.TestCase):
    def test_a_code_has_the_documented_length(self):
        self.assertEqual(len(Pairing().open()), CODE_LENGTH)

    def test_codes_avoid_lookalike_characters(self):
        pairing = Pairing()
        codes = "".join(pairing.open() for _ in range(40))
        for bad in "01OIL":
            self.assertNotIn(bad, codes)

    def test_a_code_is_single_use(self):
        pairing = Pairing()
        code = pairing.open()
        self.assertIsNotNone(pairing.claim(code))
        self.assertIsNone(pairing.claim(code), "a claimed code must not work twice")

    def test_an_unknown_code_is_refused(self):
        self.assertIsNone(Pairing().claim("ZZZZZZ"))

    def test_a_code_can_be_typed_in_any_case_or_spacing(self):
        pairing = Pairing()
        code = pairing.open()
        messy = f" {code[:3].lower()}-{code[3:].lower()} "
        self.assertIsNotNone(pairing.claim(messy))

    def test_an_expired_code_is_refused(self):
        pairing = Pairing()
        code = pairing.open()
        pairing._pending[code]["created"] = time.time() - 400
        self.assertIsNone(pairing.claim(code))

    def test_cancelling_removes_a_code(self):
        pairing = Pairing()
        code = pairing.open()
        self.assertTrue(pairing.cancel(code))
        self.assertIsNone(pairing.claim(code))

    def test_opening_many_codes_does_not_grow_without_bound(self):
        pairing = Pairing()
        for _ in range(20):
            pairing.open()
        self.assertLessEqual(len(pairing.pending()), 5)


class TokenTest(unittest.TestCase):
    def test_claiming_returns_a_token_that_verifies(self):
        pairing = Pairing()
        token = pairing.claim(pairing.open())
        device = pairing.verify(token)
        self.assertIsNotNone(device)

    def test_the_token_is_not_stored_in_recoverable_form(self):
        pairing = Pairing()
        token = pairing.claim(pairing.open())
        stored = "".join(d.token_hash for d in pairing.devices.values())
        self.assertNotIn(token, stored)
        self.assertEqual(len(stored), 64, "expected a sha256 hex digest")

    def test_a_wrong_token_is_refused(self):
        pairing = Pairing()
        pairing.claim(pairing.open())
        self.assertIsNone(pairing.verify("not-a-real-token"))

    def test_an_empty_token_is_refused(self):
        self.assertIsNone(Pairing().verify(""))

    def test_verify_records_last_seen(self):
        pairing = Pairing()
        token = pairing.claim(pairing.open())
        first = pairing.verify(token).last_seen
        self.assertGreater(first, 0.0, "a check-in should be timestamped")
        time.sleep(0.01)
        self.assertGreater(pairing.verify(token).last_seen, first,
                           "each check-in should advance last_seen")

    def test_a_revoked_device_stops_working(self):
        pairing = Pairing()
        token = pairing.claim(pairing.open())
        device = pairing.verify(token)
        self.assertTrue(pairing.revoke(device.id))
        self.assertIsNone(pairing.verify(token))

    def test_revoking_an_unknown_device_reports_failure(self):
        self.assertFalse(Pairing().revoke("nope"))

    def test_revoke_all_clears_every_device(self):
        pairing = Pairing()
        tokens = [pairing.claim(pairing.open()) for _ in range(3)]
        self.assertEqual(pairing.revoke_all(), 3)
        for token in tokens:
            self.assertIsNone(pairing.verify(token))


class PersistenceTest(unittest.TestCase):
    def test_devices_survive_a_restart(self):
        store = tmp_store()
        pairing = Pairing(store)
        token = pairing.claim(pairing.open())

        reloaded = Pairing(store)
        self.assertIsNotNone(reloaded.verify(token), "pairing must survive a restart")

    def test_pending_codes_do_not_survive_a_restart(self):
        store = tmp_store()
        pairing = Pairing(store)
        code = pairing.open()

        reloaded = Pairing(store)
        self.assertIsNone(reloaded.claim(code),
                          "an unwatched code should not outlive the process")

    def test_a_device_without_a_hash_is_ignored(self):
        store = tmp_store()
        store.devices = [{"id": "x", "name": "broken", "token_hash": ""}]
        self.assertEqual(len(Pairing(store).devices), 0)

    def test_device_json_round_trips(self):
        original = Device(id="a", name="phone", token_hash="f" * 64, paired_by="1")
        self.assertEqual(Device.from_json(original.to_json()).to_json(),
                         original.to_json())


class NormaliseTest(unittest.TestCase):
    def test_strips_separators_and_case(self):
        self.assertEqual(normalise(" ab-c d "), "ABCD")


if __name__ == "__main__":
    unittest.main()


class PairCommandTest(unittest.TestCase):
    """`+pair` is the operator's half of pairing, so it is driven for real."""

    def setUp(self):
        from .test_engine import build_engine
        self.tmp = tempfile.mkdtemp()
        self.engine, self.rest = build_engine(self.tmp)

    def _run(self, text: str, user_id: int = None):
        from freehands.commands import parse
        from freehands.config import OWNER_ID
        cmd = parse(text)
        self.assertIsNotNone(cmd, f"{text} did not parse")
        self.engine.dispatch(cmd, user_id or OWNER_ID, 1, 555, set())

    def _last(self) -> str:
        return self.rest.replies[-1]["content"]

    def test_pair_without_a_code_issues_one(self):
        self._run("+pair")
        body = self._last()
        self.assertIn("Pairing code", body)
        self.assertEqual(len(self.engine.pairing.pending()), 1)

    def test_the_issued_code_can_be_claimed(self):
        self._run("+pair")
        code = self.engine.pairing.pending()[0][0]
        self._run(f"+pair {code}")
        self.assertIn("Paired", self._last())
        self.assertEqual(len(self.engine.pairing.devices), 1)

    def test_the_token_is_shown_exactly_once(self):
        self._run("+pair")
        code = self.engine.pairing.pending()[0][0]
        self._run(f"+pair {code}")
        token = self.engine.pairing.devices and self._last().split("`")[3]
        self.assertIsNotNone(self.engine.pairing.verify(token))
        # Running the same code again must not hand out the token twice.
        self._run(f"+pair {code}")
        self.assertNotIn("Token, shown once", self._last())

    def test_a_bad_code_is_reported_not_silently_ignored(self):
        self._run("+pair ZZZZZZ")
        self.assertIn("No code", self._last())

    def test_a_non_operator_cannot_pair(self):
        self._run("+pair", user_id=1234)
        self.assertIn("permission", self._last().lower())
        self.assertEqual(len(self.engine.pairing.pending()), 0)

    def test_devices_lists_a_paired_console(self):
        self._run("+pair")
        code = self.engine.pairing.pending()[0][0]
        self._run(f"+pair {code}")
        self._run("+devices")
        self.assertIn("Paired consoles", self._last())

    def test_devices_with_nothing_paired_says_so(self):
        self._run("+devices")
        self.assertIn("No consoles paired", self._last())

    def test_revoke_all_disconnects_everything(self):
        self._run("+pair")
        self._run(f"+pair {self.engine.pairing.pending()[0][0]}")
        self._run("+revoke all")
        self.assertIn("Revoked", self._last())
        self.assertEqual(len(self.engine.pairing.devices), 0)

    def test_revoking_one_device_leaves_the_others(self):
        for _ in range(2):
            self._run("+pair")
            self._run(f"+pair {self.engine.pairing.pending()[0][0]}")
        first = sorted(self.engine.pairing.devices)[0]
        self._run(f"+revoke {first}")
        self.assertEqual(len(self.engine.pairing.devices), 1)
