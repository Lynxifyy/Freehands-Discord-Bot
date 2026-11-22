"""The console app explains every command, so every command needs a description."""

from __future__ import annotations

import unittest

from freehands.command_docs import DETAILS, detail_for
from freehands.commands import Registry
from freehands import cmd_impl


class _Engine:
    registry = Registry()

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _commands():
    registry = Registry()
    engine = _Engine()
    engine.registry = registry
    cmd_impl.register(engine)
    return {spec.name: spec for spec in registry.all()}


class CommandDocsTest(unittest.TestCase):
    def test_every_command_has_a_description(self):
        missing = sorted(set(_commands()) - set(DETAILS))
        self.assertEqual(missing, [], f"no description for: {missing}")

    def test_no_description_for_a_command_that_does_not_exist(self):
        stale = sorted(set(DETAILS) - set(_commands()))
        self.assertEqual(stale, [], f"description for unknown command: {stale}")

    def test_descriptions_are_plain_sentences(self):
        for name, text in DETAILS.items():
            with self.subTest(command=name):
                self.assertGreater(len(text), 40, "description is too short to explain")
                self.assertTrue(text.endswith("."), "description should end with a full stop")
                self.assertFalse(
                    any(c in text for c in "`*_#"),
                    "description should be plain text, not markup",
                )

    def test_detail_falls_back_to_summary(self):
        self.assertEqual(detail_for("not_a_command", "a short summary"), "a short summary")
        self.assertEqual(detail_for("not_a_command"), "No description written yet.")

    def test_detail_prefers_the_written_text(self):
        self.assertIn("ban protection", detail_for("antiban", "ignored"))


if __name__ == "__main__":
    unittest.main()
