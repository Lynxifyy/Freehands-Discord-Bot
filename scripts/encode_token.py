"""Store a Discord bot token where the bot can read it, and nowhere else.

This used to print an obfuscated blob to paste into `vault.py`. That is not a
secret-handling strategy: the repository is public, the decoder sits next to
the blob, and anyone who can read the file can recover the token. The bot now
reads `bot/.token`, which is gitignored, or `FH_TOKEN` from the environment.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))

from freehands.vault import token_path  # noqa: E402


def _looks_like_token(text: str) -> bool:
    parts = text.strip().split(".")
    return len(parts) == 3 and all(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--token")
    source.add_argument("--from-file")
    parser.add_argument("--check", action="store_true",
                        help="report whether a token is resolvable, without printing it")
    args = parser.parse_args()

    if args.check:
        from freehands.vault import MissingToken, load_token

        try:
            token = load_token()
        except MissingToken as exc:
            print(f"no token: {exc}")
            return 1
        print(f"token resolves ({len(token)} chars, ends {token[-4:]})")
        return 0

    token = args.token
    if args.from_file:
        token = Path(args.from_file).read_text(encoding="utf-8").strip()
    if not token:
        parser.error("provide --token or --from-file")
    if not _looks_like_token(token):
        parser.error("that does not look like a Discord bot token")

    path = token_path()
    path.write_text(token.strip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"wrote {path}")
    print("It is gitignored. Do not paste it into a tracked file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
