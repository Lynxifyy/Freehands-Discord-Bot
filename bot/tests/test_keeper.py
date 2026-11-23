"""The keeper is what lets a paired phone recover a dead supervisor.

These test the decision logic, not the process spawning: whether to wake, how
the port is found, and the two failure modes that made the old build lie.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from freehands import keeper  # noqa: E402


class PortDiscoveryTest(unittest.TestCase):
    def test_published_port_wins_over_the_environment(self):
        """The bot may be started without the supervisor's env.

        Guessing from the environment had the keeper watch 8790 while the
        supervisor was on 12000, so it saw "down" forever and would have
        spawned a second supervisor on the wrong port.
        """
        with tempfile.TemporaryDirectory() as tmp:
            portfile = Path(tmp) / "console.port"
            portfile.write_text("12000")
            with unittest.mock.patch.object(keeper, "PORTFILE", portfile), \
                    unittest.mock.patch.dict(os.environ, {"FH_CONSOLE_PORT": "8790"}):
                self.assertEqual(keeper.supervisor_port(), 12000)
                self.assertEqual(keeper.supervisor_url(), "http://127.0.0.1:12000")

    def test_falls_back_to_env_when_nothing_is_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.object(keeper, "PORTFILE", Path(tmp) / "absent"), \
                    unittest.mock.patch.dict(os.environ, {"FH_CONSOLE_PORT": "12000"}):
                self.assertEqual(keeper.supervisor_port(), 12000)

    def test_garbage_in_the_port_file_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            portfile = Path(tmp) / "console.port"
            portfile.write_text("not a port")
            with unittest.mock.patch.object(keeper, "PORTFILE", portfile), \
                    unittest.mock.patch.dict(os.environ, {"FH_CONSOLE_PORT": "8790"}):
                self.assertEqual(keeper.supervisor_port(), 8790)

    def test_a_zero_port_is_ignored(self):
        """`0` means "any port" — what a test run binds, not a real address.

        The supervisor published it once because a test called main(serve=False)
        with port 0. Every later reader took it at face value, so the keeper
        spawned supervisors that nothing could connect to, once per interval,
        for as long as the bot lived.
        """
        with tempfile.TemporaryDirectory() as tmp:
            portfile = Path(tmp) / "console.port"
            portfile.write_text("0")
            with unittest.mock.patch.object(keeper, "PORTFILE", portfile), \
                    unittest.mock.patch.dict(os.environ, {"FH_CONSOLE_PORT": "12000"}):
                self.assertEqual(keeper.supervisor_port(), 12000)

    def test_an_out_of_range_port_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            portfile = Path(tmp) / "console.port"
            portfile.write_text("99999")
            with unittest.mock.patch.object(keeper, "PORTFILE", portfile), \
                    unittest.mock.patch.dict(os.environ, {"FH_CONSOLE_PORT": "12000"}):
                self.assertEqual(keeper.supervisor_port(), 12000)


class WatchDecisionTest(unittest.TestCase):
    def test_a_healthy_supervisor_is_left_alone(self):
        calls = []
        stop = threading.Event()

        def fake_sleep(_):
            stop.set()  # run exactly one pass

        with unittest.mock.patch.object(keeper, "supervisor_up", lambda *a, **k: True), \
                unittest.mock.patch.object(keeper, "spawn_supervisor", lambda: calls.append(1)), \
                unittest.mock.patch.object(time, "sleep", fake_sleep):
            keeper.watch(stop=stop)
        self.assertEqual(calls, [])

    def test_a_dead_supervisor_is_restarted_after_the_grace_period(self):
        """One missed check is not enough — a restarting supervisor looks dead."""
        spawns = []
        clock = {"t": 1000.0}

        def fake_sleep(_):
            clock["t"] += 60.0
            if len(spawns) >= 1:
                raise SystemExit  # end the loop once it has acted

        with unittest.mock.patch.object(keeper, "supervisor_up", lambda *a, **k: False), \
                unittest.mock.patch.object(keeper, "spawn_supervisor",
                                           lambda: spawns.append(clock["t"])), \
                unittest.mock.patch.object(time, "sleep", fake_sleep), \
                unittest.mock.patch.object(time, "time", lambda: clock["t"]):
            try:
                keeper.watch(interval=30.0, grace=45.0)
            except SystemExit:
                pass
        self.assertEqual(len(spawns), 1)
        # First pass only arms the timer; the spawn happens after the grace.
        self.assertGreaterEqual(spawns[0], 1000.0 + 45.0)

    def test_a_failing_check_never_takes_the_bot_down(self):
        """A keeper that raises would kill the bot it exists to protect."""
        calls = []

        def boom(*_a, **_k):
            calls.append(1)
            raise OSError("network is down")

        def fake_sleep(_):
            if len(calls) >= 2:
                raise SystemExit

        with unittest.mock.patch.object(keeper, "supervisor_up", boom), \
                unittest.mock.patch.object(time, "sleep", fake_sleep):
            try:
                keeper.watch(interval=1.0, grace=1.0)
            except SystemExit:
                pass
        self.assertGreaterEqual(len(calls), 2)


class SpawnTest(unittest.TestCase):
    def test_spawning_uses_the_published_port(self):
        """A keeper-started supervisor must bind where the public host forwards."""
        captured = {}

        class FakeProc:
            pid = 4321

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env") or {}
            return FakeProc()

        with tempfile.TemporaryDirectory() as tmp:
            portfile = Path(tmp) / "console.port"
            portfile.write_text("12000")
            with unittest.mock.patch.object(keeper, "PORTFILE", portfile), \
                    unittest.mock.patch.object(keeper, "ROOT", Path(tmp)), \
                    unittest.mock.patch.object(keeper, "SUPERVISOR", Path(tmp) / "console_api.py"), \
                    unittest.mock.patch("subprocess.Popen", fake_popen):
                (Path(tmp) / "console_api.py").write_text("# stub")
                (Path(tmp) / "bot").mkdir()
                keeper.spawn_supervisor()
        self.assertEqual(captured["env"]["FH_CONSOLE_PORT"], "12000")

    def test_a_missing_supervisor_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.object(keeper, "SUPERVISOR", Path(tmp) / "nope.py"):
                self.assertIsNone(keeper.spawn_supervisor())


if __name__ == "__main__":
    unittest.main()
