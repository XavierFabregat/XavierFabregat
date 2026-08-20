#!/usr/bin/env python3
"""Checks on the panel's alignment invariants.

Every row is padded by hand to a fixed column count, and a row that is one
character short looks fine in isolation while leaving the panel visibly ragged.
The Wakatime section makes that worse: it only renders when a key is present,
so a fault there stays hidden until the workflow runs. These checks cover it
with a stubbed response instead, and need no credential.

    python scripts/test_render.py
"""

import importlib.util
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("render_readme", ROOT / "scripts" / "render_readme.py")
rr = importlib.util.module_from_spec(spec)
sys.modules["render_readme"] = rr
spec.loader.exec_module(rr)

SGR = re.compile(r"\x1b\[[0-9;]*m")
plain = lambda s: SGR.sub("", s)

# A trimmed copy of /users/current/stats/last_7_days, with a name past the
# column width and an entry at 100 percent to push the bar to full width.
WAKATIME_STUB = {"data": {"languages": [
    {"name": "TypeScript", "percent": 61.42, "text": "18 hrs 44 mins"},
    {"name": "Rust", "percent": 19.03, "text": "5 hrs 48 mins"},
    {"name": "Markdown", "percent": 4.22, "text": "1 hr 17 mins"},
    {"name": "Objective-C++ with a silly long name", "percent": 100.0, "text": "99 hrs 59 mins"},
]}}

failures = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def test_rows_fill_the_panel() -> None:
    widths = {len(plain(line)) for line in rr.build_panel() if plain(line).strip()}
    check(widths == {rr.PANEL_WIDTH},
          f"panel rows should all be {rr.PANEL_WIDTH} wide, got {sorted(widths)}")


def test_wakatime_rows_fill_the_panel() -> None:
    os.environ["WAKATIME_API_KEY"] = "stub"
    original = rr.get_json
    rr.get_json = lambda url, headers: WAKATIME_STUB
    try:
        rows = rr.wakatime_bars(limit=4)
    finally:
        rr.get_json = original
        del os.environ["WAKATIME_API_KEY"]

    check(rows is not None and len(rows) == 4, "expected four language rows")
    widths = {len(plain(line)) for line in rows or []}
    check(widths == {rr.PANEL_WIDTH},
          f"wakatime rows should all be {rr.PANEL_WIDTH} wide, got {sorted(widths)}")


def test_long_value_is_reported() -> None:
    row = rr.row("A label", "x" * rr.PANEL_WIDTH)
    check(len(plain(row)) > rr.PANEL_WIDTH,
          "an over-long value should overflow rather than silently truncate")


def test_every_colour_resets() -> None:
    body = "\n".join(rr.build_panel())
    opens = len(re.findall(r"\x1b\[(?!0m)[0-9;]*m", body))
    resets = len(re.findall(r"\x1b\[0m", body))
    check(opens == resets, f"{opens} colour opens but {resets} resets; colour would bleed")


def test_no_trailing_whitespace() -> None:
    rendered = rr.compose()
    bad = [i for i, line in enumerate(rendered.split("\n"), 1)
           if plain(line) != plain(line).rstrip()]
    check(not bad, f"trailing whitespace on lines {bad}")


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("alignment invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
