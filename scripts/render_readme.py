#!/usr/bin/env python3
"""Render README.md: a neofetch-style panel next to the ASCII portrait.

GitHub renders ANSI escape codes inside a fenced block tagged ``ansi``, which
is the only way to get colour into a README without shipping an image.

Only the 16 basic ANSI colours are used. GitHub maps those to its own theme
palette, so the block stays legible in light and dark mode; 256-colour and
24-bit codes are fixed RGB and would be unreadable in one theme or the other.
Values are printed with no colour at all so they inherit the reader's
foreground colour.

Usage:
    ./scripts/render_readme.py            # write README.md
    ./scripts/render_readme.py --check    # exit 1 if README.md is stale
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTRAIT = ROOT / "assets" / "portrait.txt"
README = ROOT / "README.md"

LOGIN = "XavierFabregat"
PANEL_WIDTH = 52
GUTTER = 2

# Set to a YYYY-MM-DD string to show an "Uptime" line; None hides it.
BIRTHDAY = "1998-01-27"

IDENTITY = [
    ("Status", "Running (stable)", "green"),
    ("OS", "Xavier Fabregat Pous", None),
    ("Host", "Barcelona, ES (local)", None),
    ("Kernel", "Full Stack Developer @ Haddock (YC W22)", None),
    ("Background", "BSc Physics, Univ. de Barcelona", None),
    ("Shell", "zsh, Neovim, Ghostty", None),
    ("Languages.Programming", "TypeScript, Rust, SQL", None),
    ("Languages.Real", "Català, Español, English", None),
]

STACK = [
    ("Frontend", "React, Next.js, React Native, Svelte"),
    ("Backend", "Node.js, Express, Koa"),
    ("Data", "PostgreSQL, MongoDB, DynamoDB"),
    ("Cloud", "AWS Lambda, API Gateway, Cognito, CDN"),
    ("Currently", "learning Rust, chasing lower levels"),
]

CONTACT = [
    ("Portfolio", "xavifabregat.dev"),
    ("Email", "xavi.fabregat.pous@gmail.com"),
    ("LinkedIn", "in/xavier-fabregat"),
]

ESC = "\x1b["
RESET = f"{ESC}0m"
COLORS = {
    "gray": f"{ESC}90m",
    "cyan": f"{ESC}36m",
    "bright_cyan": f"{ESC}96m",
    "green": f"{ESC}32m",
    "yellow": f"{ESC}33m",
    "magenta": f"{ESC}35m",
    "bold": f"{ESC}1m",
    None: "",
}


def paint(text: str, color: str | None) -> str:
    return f"{COLORS[color]}{text}{RESET}" if color else text


def visible_len(text: str) -> int:
    out, i = 0, 0
    while i < len(text):
        if text[i] == "\x1b":
            i = text.find("m", i) + 1
            continue
        out += 1
        i += 1
    return out


def header(title: str) -> str:
    """`xavi@github ──────────` — the top line of the panel."""
    user, host = title.split("@")
    label = paint(user, "bold") + paint("@", "gray") + paint(host, "cyan")
    rule = "─" * max(1, PANEL_WIDTH - visible_len(label) - 1)
    return f"{label} {paint(rule, 'gray')}"


def section(title: str) -> str:
    """`- Contact ────────────` — a divider between groups."""
    label = paint(f"- {title} ", "bright_cyan")
    rule = "─" * max(1, PANEL_WIDTH - visible_len(label))
    return f"{label}{paint(rule, 'gray')}"


def row(label: str, value: str, color: str | None = None) -> str:
    """`  Label: ......... value` with the value flush right."""
    left = f"  {label}:"
    slack = PANEL_WIDTH - len(left) - len(value) - 2
    if slack < 1:
        print(f"'{label}' overflows the panel by {1 - slack} chars; it will not "
              "line up with the section rules", file=sys.stderr)
    dots = "." * max(1, slack)
    return f"{paint(left, 'cyan')} {paint(dots, 'gray')} {paint(value, color)}"


def uptime(birthday: str) -> str:
    """Years, months and days, counted on the calendar rather than in 30-day
    blocks, so the day figure agrees with what a person would count."""
    born = date.fromisoformat(birthday)
    today = date.today()

    months = (today.year - born.year) * 12 + today.month - born.month
    if today.day < born.day:
        months -= 1

    # the most recent month-boundary anniversary, clamped for short months
    anniversary_year = born.year + (born.month - 1 + months) // 12
    anniversary_month = (born.month - 1 + months) % 12 + 1
    last_day = monthrange(anniversary_year, anniversary_month)[1]
    anniversary = date(anniversary_year, anniversary_month, min(born.day, last_day))

    days = (today - anniversary).days
    return f"{months // 12} years, {months % 12} months, {days} days"


def gh_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    try:  # local runs: borrow the gh CLI's token
        return subprocess.run(["gh", "auth", "token"], capture_output=True,
                              text=True, check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def post_json(url: str, payload: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def get_json(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def github_stats() -> list[tuple[str, str]] | None:
    token = gh_token()
    if not token:
        print("no GitHub token; skipping stats section", file=sys.stderr)
        return None
    query = """
    query($login:String!) {
      user(login:$login) {
        followers { totalCount }
        repositories(first:100, ownerAffiliations:OWNER, privacy:PUBLIC) {
          totalCount
          nodes { stargazerCount }
        }
        contributionsCollection {
          totalCommitContributions
          restrictedContributionsCount
          totalPullRequestContributions
          contributionCalendar { totalContributions }
        }
      }
    }"""
    try:
        data = post_json("https://api.github.com/graphql",
                         {"query": query, "variables": {"login": LOGIN}},
                         {"Authorization": f"bearer {token}"})
        user = data["data"]["user"]
    except (urllib.error.URLError, KeyError, TypeError) as exc:
        print(f"GitHub stats unavailable: {exc}", file=sys.stderr)
        return None

    contrib = user["contributionsCollection"]
    stars = sum(n["stargazerCount"] for n in user["repositories"]["nodes"])
    commits = contrib["totalCommitContributions"] + contrib["restrictedContributionsCount"]
    return [
        ("Repos", f"{user['repositories']['totalCount']} public"),
        ("Stars", str(stars)),
        ("Followers", str(user["followers"]["totalCount"])),
        ("Commits (1y)", f"{commits:,}"),
        ("Pull requests (1y)", f"{contrib['totalPullRequestContributions']}"),
        ("Contributions (1y)", f"{contrib['contributionCalendar']['totalContributions']:,}"),
    ]


def wakatime_bars(limit: int = 4, bar_width: int = 14) -> list[str] | None:
    key = os.environ.get("WAKATIME_API_KEY")
    if not key:
        print("no WAKATIME_API_KEY; skipping coding-time section", file=sys.stderr)
        return None
    auth = base64.b64encode(key.encode()).decode()
    try:
        data = get_json("https://wakatime.com/api/v1/users/current/stats/last_7_days",
                        {"Authorization": f"Basic {auth}"})
        languages = data["data"]["languages"][:limit]
    except (urllib.error.URLError, KeyError, TypeError) as exc:
        print(f"Wakatime unavailable: {exc}", file=sys.stderr)
        return None

    lines = []
    for lang in languages:
        pct = float(lang.get("percent", 0))
        filled = round(pct / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        name = lang["name"][:14]
        text = lang.get("text", "")
        left = f"  {name:<14} {paint(bar, 'magenta')}"
        # no -1 here: unlike row(), nothing is appended after the value, so the
        # padding is the only thing between the bar and the panel's right edge
        pad = " " * max(1, PANEL_WIDTH - visible_len(left) - len(text))
        lines.append(f"{left}{pad}{text}")
    return lines


def pad_visible(text: str, width: int) -> str:
    return text + " " * max(0, width - visible_len(text))


def centre_visible(text: str, width: int) -> str:
    slack = max(0, width - visible_len(text))
    return " " * (slack // 2) + text


def palette() -> list[str]:
    """The colour swatches neofetch prints under its logo.

    Black and bright-black are skipped: GitHub maps them to a near-background
    colour, so they read as gaps in the strip rather than swatches.
    """
    return [
        "".join(f"{ESC}{code}m███{RESET}" for code in range(31, 38)),
        "".join(f"{ESC}{code}m███{RESET}" for code in range(91, 98)),
    ]


def build_panel() -> list[str]:
    lines = [header("xavi@github")]
    for label, value, color in IDENTITY:
        lines.append(row(label, value, color))
        if label == "Host" and BIRTHDAY:
            lines.append(row("Uptime", uptime(BIRTHDAY)))

    lines += ["", section("Stack")]
    lines += [row(label, value) for label, value in STACK]

    lines += ["", section("Contact")]
    lines += [row(label, value) for label, value in CONTACT]

    stats = github_stats()
    if stats:
        lines += ["", section("GitHub")]
        lines += [row(label, value, "yellow") for label, value in stats]

    bars = wakatime_bars()
    if bars:
        lines += ["", section("Last 7 days of coding")]
        lines += bars

    return lines


def compose() -> str:
    portrait = PORTRAIT.read_text().rstrip("\n").split("\n")
    art_width = max(len(line) for line in portrait)
    left_column = (
        [paint(line, "gray") if line.strip() else "" for line in portrait]
        + [""]
        + [centre_visible(swatch, art_width) for swatch in palette()]
    )
    panel = build_panel()

    body = []
    for i in range(max(len(left_column), len(panel))):
        left = left_column[i] if i < len(left_column) else ""
        right = panel[i] if i < len(panel) else ""
        # with nothing on the right there is nothing to align to, so skip the
        # padding entirely rather than leave trailing spaces behind an escape
        body.append(f"{pad_visible(left, art_width)}{' ' * GUTTER}{right}" if right else left)

    block = "\n".join(body)
    return (
        "```ansi\n"
        f"{block}\n"
        "```\n"
        "\n"
        f"[![Portfolio](https://img.shields.io/badge/portfolio-xavifabregat.dev-0891b2?style=flat-square&labelColor=1c1917)](https://xavifabregat.dev)\n"
        f"[![LinkedIn](https://img.shields.io/badge/linkedin-xavier--fabregat-0a66c2?style=flat-square&labelColor=1c1917)](https://www.linkedin.com/in/xavier-fabregat-0a198a231/)\n"
        f"[![GitHub followers](https://img.shields.io/github/followers/{LOGIN}?logo=github&style=flat-square&color=0891b2&labelColor=1c1917)](https://www.github.com/{LOGIN})\n"
        "\n"
        "<!-- Generated by scripts/render_readme.py - edit that, not this file. -->\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if README.md differs from the rendered output")
    args = ap.parse_args()

    rendered = compose()
    if args.check:
        current = README.read_text() if README.exists() else ""
        if current != rendered:
            print("README.md is stale; run scripts/render_readme.py", file=sys.stderr)
            return 1
        print("README.md is up to date")
        return 0

    README.write_text(rendered)
    print(f"wrote {README.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
