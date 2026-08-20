#!/usr/bin/env python3
"""Point assets/neofetch.json at a commit-pinned URL for the portrait.

Three separate caches sit between a committed file and the rendered card: the
generator caches its response, it caches the config it fetched, and
raw.githubusercontent caches branch paths for minutes. A branch URL like
.../main/assets/portrait.png therefore keeps serving the previous portrait long
after the new one is pushed, which looks exactly like the generator ignoring
the change.

A URL pinned to the commit that last touched the file is immutable, so it is
never stale and never needs busting: a new portrait is a new commit, hence a
new URL. Run this after committing a new portrait, then commit the config it
rewrites.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "XavierFabregat/XavierFabregat"
PORTRAIT = "assets/portrait.png"


def last_commit_touching(path: str) -> str | None:
    try:
        sha = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", path],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return sha or None
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    if not (ROOT / PORTRAIT).exists():
        print(f"{PORTRAIT} is missing", file=sys.stderr)
        return 1

    dirty = subprocess.run(["git", "status", "--porcelain", "--", PORTRAIT],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        print(f"{PORTRAIT} has uncommitted changes; commit it first so there is a "
              "commit to pin to", file=sys.stderr)
        return 1

    sha = last_commit_touching(PORTRAIT)
    if not sha:
        print(f"no commit found for {PORTRAIT}", file=sys.stderr)
        return 1

    config = ROOT / "assets" / "neofetch.json"
    cfg = json.loads(config.read_text())
    pinned = f"https://raw.githubusercontent.com/{REPO}/{sha}/{PORTRAIT}"
    if cfg.get("image") == pinned:
        print(f"already pinned to {sha[:8]}")
        return 0

    cfg["image"] = pinned
    config.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"pinned portrait URL to {sha[:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
