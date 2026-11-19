#!/usr/bin/env python3
"""Encode a Discord bot token into the split, masked form `vault.py` decodes.

Usage:  python3 scripts/encode_token.py --token 'XXXX.XXXX.XXXX'
        python3 scripts/encode_token.py --from-file bot/.token
        python3 scripts/encode_token.py --check        # verify the blob decodes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))

from freehands.vault import SALT, mask, unmask  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--token")
    source.add_argument("--from-file")
    parser.add_argument("--check", action="store_true", help="verify the embedded blob")
    args = parser.parse_args()

    if args.check:
        decoded = unmask()
        parts = decoded.split(".")
        ok = len(parts) == 3 and all(parts)
        print(f"embedded blob decodes: {'ok' if ok else 'INVALID'} ({len(decoded)} chars)")
        return 0 if ok else 1

    token = args.token
    if args.from_file:
        token = Path(args.from_file).read_text(encoding="utf-8").strip()
    if not token:
        parser.error("provide --token or --from-file")

    fragments = mask(token, SALT)
    print("FRAGMENTS = (")
    for fragment in fragments:
        print(f'    "{fragment}",')
    print(")")
    assert unmask(tuple(fragments), SALT) == token, "round trip failed"
    print("# round trip verified", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
