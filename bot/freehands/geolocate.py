"""Turn a pairing address into something a person can read.

`+devices` is the one place an operator checks "is this phone mine?", and a raw
IPv6 string does not answer that. The address is looked up once at pairing time
and cached, because the lookup is a third-party HTTP call and pairing must not
fail when the network is down.

The result is advisory. A VPN, a carrier NAT or a phone on mobile data will all
place a device somewhere unexpected, so the country is a hint, not a proof.
"""

from __future__ import annotations

import ipaddress
import json
import threading
import time
import urllib.error
import urllib.request

from .log import log

LOOKUP_URL = "http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp"
LOOKUP_TTL = 6 * 3600.0

_cache: dict[str, tuple[float, str]] = {}
_lock = threading.Lock()


def is_private(ip: str) -> bool:
    """True for loopback, LAN and link-local addresses.

    Those cannot be geolocated, and asking a third party about them leaks
    internal network detail for no benefit.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return addr.is_private or addr.is_loopback or addr.is_link_local


def describe(ip: str) -> str:
    """A short human label for `ip`: "Manchester, United Kingdom" or similar.

    Never raises: an unknown address returns "unknown" and a private one returns
    "local network", because `+devices` should still print the row.
    """
    ip = (ip or "").strip()
    if not ip:
        return "unknown"
    if is_private(ip):
        return "local network"

    now = time.time()
    with _lock:
        hit = _cache.get(ip)
        if hit and now - hit[0] < LOOKUP_TTL:
            return hit[1]

    label = _lookup(ip)
    if label is not None:
        with _lock:
            _cache[ip] = (now, label)
    # A failed lookup is not cached: the next pairing should try again rather
    # than inherit "unknown" from a minute-long outage.
    return label or "unknown"


def _lookup(ip: str) -> str | None:
    """The location label, or None when the lookup could not be completed."""
    req = urllib.request.Request(
        LOOKUP_URL.format(ip=ip), headers={"User-Agent": "freehands-bot"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("geolocate %s failed: %r", ip, exc)
        return None

    if data.get("status") != "success":
        return None
    parts = [data.get("city"), data.get("country")]
    label = ", ".join(p for p in parts if p)
    return label or data.get("regionName") or "unknown"


def client_ip(headers, peer: str) -> str:
    """The address a request really came from.

    The supervisor sits behind a proxy, so `peer` is the proxy and the real
    address is in a forwarding header. Only the first hop is taken: the rest of
    the list is client-controlled and would let anyone claim any location.
    """
    for name in ("X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP"):
        raw = headers.get(name) if headers else None
        if raw:
            first = str(raw).split(",")[0].strip()
            if first:
                return first
    return (peer or "").strip()
