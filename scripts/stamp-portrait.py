#!/usr/bin/env python3
"""Stamp assets/neofetch.json's image URL with the portrait's content hash.

The card generator caches images by URL, so a new assets/portrait.png at the
same URL is never picked up: the card keeps rendering the previous face. Keying
the URL on the file's own hash means a changed portrait always looks like a new
URL, and an unchanged one never busts the cache needlessly.

Run this after regenerating the portrait, before refresh-cards.sh.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    portrait = ROOT / "assets" / "portrait.png"
    config = ROOT / "assets" / "neofetch.json"
    if not portrait.exists():
        print(f"{portrait} is missing", file=sys.stderr)
        return 1

    digest = hashlib.sha256(portrait.read_bytes()).hexdigest()[:8]
    cfg = json.loads(config.read_text())
    base = cfg.get("image", "").split("?")[0]
    if not base:
        print("config has no image URL to stamp", file=sys.stderr)
        return 1

    stamped = f"{base}?v={digest}"
    if cfg["image"] == stamped:
        print(f"already stamped with {digest}")
        return 0

    cfg["image"] = stamped
    config.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"stamped image URL with {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
