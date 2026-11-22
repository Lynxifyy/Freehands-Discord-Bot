"""Turning a pairing address into a location label.

`+devices` shows where a phone paired from, which is how an operator spots a
token that leaked. The lookup is a third-party HTTP call, so the interesting
properties are all about failure: it must never raise, never call out for a
private address, and never block a pairing on a slow network.
"""

from __future__ import annotations

import unittest

from freehands import geolocate


class DescribeTests(unittest.TestCase):
    def setUp(self) -> None:
        geolocate._cache.clear()
        self._real = geolocate._lookup
        geolocate._lookup = lambda ip: "Testville, Testland"

    def tearDown(self) -> None:
        geolocate._lookup = self._real
        geolocate._cache.clear()

    def test_a_public_address_is_looked_up(self):
        self.assertEqual(geolocate.describe("8.8.8.8"), "Testville, Testland")

    def test_an_empty_address_is_unknown_not_an_error(self):
        self.assertEqual(geolocate.describe(""), "unknown")

    def test_private_addresses_are_not_sent_to_a_third_party(self):
        """Asking a stranger about 192.168.x.x leaks internal detail for nothing."""
        for ip in ("192.168.1.5", "10.0.0.1", "127.0.0.1", "172.16.4.4"):
            with self.subTest(ip=ip):
                self.assertEqual(geolocate.describe(ip), "local network")

    def test_a_malformed_address_does_not_raise(self):
        self.assertEqual(geolocate.describe("not-an-ip"), "local network")

    def test_a_second_lookup_comes_from_the_cache(self):
        calls = {"n": 0}

        def counting(ip):
            calls["n"] += 1
            return "Cached, Place"

        geolocate._lookup = counting
        geolocate.describe("1.1.1.1")
        geolocate.describe("1.1.1.1")
        self.assertEqual(calls["n"], 1, "a repeated pairing address must not re-query")


class LookupFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        geolocate._cache.clear()

    def test_a_network_failure_returns_unknown(self):
        real = geolocate.urllib.request.urlopen

        def boom(*a, **k):
            raise OSError("no route to host")

        geolocate.urllib.request.urlopen = boom
        try:
            self.assertEqual(geolocate.describe("8.8.4.4"), "unknown")
        finally:
            geolocate.urllib.request.urlopen = real

    def test_a_failed_lookup_is_not_cached_as_a_location(self):
        """A transient outage must not pin "unknown" onto the device forever."""
        real = geolocate.urllib.request.urlopen

        def boom(*a, **k):
            raise OSError("down")

        geolocate.urllib.request.urlopen = boom
        try:
            geolocate.describe("9.9.9.9")
            self.assertNotIn("9.9.9.9", geolocate._cache)
        finally:
            geolocate.urllib.request.urlopen = real


class ClientIpTests(unittest.TestCase):
    """The supervisor is behind a proxy, so the peer address is the proxy."""

    def test_the_first_forwarded_hop_wins(self):
        headers = {"X-Forwarded-For": "8.8.8.8, 10.0.0.1, 10.0.0.2"}
        self.assertEqual(geolocate.client_ip(headers, "127.0.0.1"), "8.8.8.8")

    def test_real_ip_header_is_accepted(self):
        self.assertEqual(geolocate.client_ip({"X-Real-IP": "1.0.0.1"}, "127.0.0.1"),
                         "1.0.0.1")

    def test_without_headers_the_peer_is_used(self):
        self.assertEqual(geolocate.client_ip({}, "9.9.9.10"), "9.9.9.10")

    def test_a_client_cannot_forge_a_later_hop(self):
        """Only the first hop is trusted: the rest is client-controlled."""
        headers = {"X-Forwarded-For": "8.8.8.8, 6.6.6.6"}
        self.assertEqual(geolocate.client_ip(headers, "127.0.0.1"), "8.8.8.8")


if __name__ == "__main__":
    unittest.main()
