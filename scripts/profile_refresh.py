#!/usr/bin/env python3
"""
profile_refresh.py - regenerate the self-updating profile artwork, no GitHub Actions needed.

Replaces the three workflows (metrics.yml, snake.yml and the refresh half of
radar.yml) for when Actions + METRICS_TOKEN aren't wired up. Everything here is
drawn from public data, so no token is required:

    python scripts/profile_refresh.py --user aadhya-07 --out assets

Writes into <out>:
    metrics.isocalendar.svg        3D isometric contribution calendar
    snake-dark.svg / snake.svg     snake eating the contribution graph
    metrics.languages-dark.svg / metrics.languages-light.svg
    card-stats-*.svg               via cards.py, with real contribution tiles
    radar-langs-*.svg              via radar.py, live language radar
    card-<repo>-*.svg              via cards.py, refreshed stars/forks

Data sources: the public contributions graph page (no auth) and the REST API.
Re-run any time to refresh; the numbers track reality on every run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

UA = {"User-Agent": "profile_refresh.py"}

# GitHub contribution greens
GREENS_DARK = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
GREENS_LIGHT = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]

THEMES = {
    "dark": {"bg": "#0d1117", "border": "#30363d", "title": "#e6edf3",
             "text": "#c9d1d9", "muted": "#8b949e", "accent": "#39d353"},
    "light": {"bg": "#ffffff", "border": "#d0d7de", "title": "#1f2328",
              "text": "#1f2328", "muted": "#57606a", "accent": "#1a7f37"},
}

FONT = "ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,sans-serif"


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #

def fetch_contributions(user: str) -> list[dict]:
    """Parse the public contributions graph page into [{date, count, level}]."""
    url = f"https://github.com/users/{user}/contributions"
    req = urllib.request.Request(url, headers=UA)
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    cells = re.findall(
        r'<td[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d)"[^>]*>'
        r".*?</td>\s*<tool-tip[^>]*>((?:\d+|No) contributions? on[^<]*)</tool-tip>",
        html, re.S)
    days = []
    for date, level, tip in cells:
        m = re.match(r"(\d+|No)", tip)
        count = 0 if m.group(1) == "No" else int(m.group(1))
        days.append({"date": date, "count": count, "level": int(level)})
    days.sort(key=lambda d: d["date"])
    if not days:
        sys.exit("could not parse any contribution days from " + url)
    return days


def streaks(days: list[dict]) -> tuple[int, int, int]:
    total = sum(d["count"] for d in days)
    counts = [d["count"] for d in days]
    # current streak: allow today to be empty, then count back
    i = len(counts) - 1
    if counts[i] == 0:
        i -= 1
    cur = 0
    while i >= 0 and counts[i] > 0:
        cur += 1
        i -= 1
    longest, run = 0, 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    return total, cur, longest


def fetch_languages(user: str) -> dict[str, int]:
    """Aggregate language bytes across public repos (REST, no token)."""
    def get(path):
        req = urllib.request.Request(f"https://api.github.com{path}", headers=UA)
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    totals: dict[str, int] = {}
    for repo in get(f"/users/{user}/repos?per_page=100&type=owner"):
        if repo.get("fork"):
            continue
        if repo.get("name", "").lower() == user.lower():
            continue  # magic profile repo: infrastructure, not work
        try:
            for lang, n in get(f"/repos/{user}/{repo['name']}/languages").items():
                totals[lang] = totals.get(lang, 0) + n
        except Exception:
            continue
    return totals


# --------------------------------------------------------------------------- #
# svg helpers
# --------------------------------------------------------------------------- #

def shade(hexcolor: str, f: float) -> str:
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"#{int(r * f):02x}{int(g * f):02x}{int(b * f):02x}"


def svg_open(w, h, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}" role="img" aria-label="{label}" '
            f'font-family="{FONT}">')


# --------------------------------------------------------------------------- #
# 3D isometric contribution calendar
# --------------------------------------------------------------------------- #

def render_isocalendar(days: list[dict], total: int) -> str:
    # group into weeks (columns), oldest first; pad the first week to 7 rows
    weeks: list[list[dict]] = []
    cur: list[dict] = []
    first_wd = dt.date.fromisoformat(days[0]["date"]).weekday()  # Mon=0
    # GitHub grid starts on Sunday; weekday() Mon=0 -> Sun offset:
    pad = (first_wd + 1) % 7
    cur = [{"level": 0}] * pad
    for d in days:
        cur.append(d)
        if len(cur) == 7:
            weeks.append(cur)
            cur = []
    if cur:
        weeks.append(cur + [{"level": 0}] * (7 - len(cur)))

    cell = 13
    h2 = cell * 0.52          # vertical half-step of the diamond
    unit_h = 9               # px of box height per level
    max_h = 4 * unit_h
    top_pad = 92
    left_pad = 30

    def proj(i, j):
        # dimetric projection of grid cell (week i, weekday j);
        # +7 shifts the (i - j) range fully on-canvas
        return (left_pad + (i - j + 7) * cell, top_pad + (i + j) * h2)

    W = int((len(weeks) + 14) * cell + left_pad * 2)
    H = int(top_pad + (len(weeks) + 7) * h2 + max_h + 46)

    parts = [svg_open(W, H, "3D isometric contribution calendar")]
    th = THEMES["dark"]
    parts.append(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="10" '
                 f'fill="{th["bg"]}" stroke="{th["border"]}"/>')
    parts.append(f'<text x="24" y="34" font-size="15" font-weight="600" '
                 f'fill="{th["title"]}">contribution calendar</text>')
    parts.append(f'<text x="{W - 24}" y="34" font-size="13" text-anchor="end" '
                 f'fill="{th["muted"]}">{total} in the last year</text>')

    # month labels along the top edge
    seen = set()
    for i, wk in enumerate(weeks):
        for d in wk:
            if not d.get("date"):
                continue
            dt_d = dt.date.fromisoformat(d["date"])
            if dt_d.day <= 7 and dt_d.month not in seen:
                seen.add(dt_d.month)
                x, y = proj(i, 0)
                if x > 70:  # keep clear of the title
                    parts.append(f'<text x="{x:.1f}" y="{y - max_h - 12:.1f}" '
                                 f'font-size="10" fill="{th["muted"]}">'
                                 f'{dt_d.strftime("%b")}</text>')

    # draw far-to-near so nearer boxes overlap correctly
    order = sorted(((i, j) for i in range(len(weeks)) for j in range(7)),
                   key=lambda t: (t[0] + t[1], t[0]))
    for i, j in order:
        lvl = weeks[i][j]["level"]
        x, y = proj(i, j)
        h = lvl * unit_h
        top_c = GREENS_DARK[lvl]
        # top diamond
        t = f"{x:.1f},{y - h:.1f} {x + cell:.1f},{y + h2 - h:.1f} {x:.1f},{y + 2 * h2 - h:.1f} {x - cell:.1f},{y + h2 - h:.1f}"
        parts.append(f'<polygon points="{t}" fill="{top_c}"/>')
        if h > 0:
            # left face
            l = (f"{x - cell:.1f},{y + h2 - h:.1f} {x:.1f},{y + 2 * h2 - h:.1f} "
                 f"{x:.1f},{y + 2 * h2:.1f} {x - cell:.1f},{y + h2:.1f}")
            # right face
            r = (f"{x + cell:.1f},{y + h2 - h:.1f} {x:.1f},{y + 2 * h2 - h:.1f} "
                 f"{x:.1f},{y + 2 * h2:.1f} {x + cell:.1f},{y + h2:.1f}")
            parts.append(f'<polygon points="{l}" fill="{shade(top_c, 0.72)}"/>')
            parts.append(f'<polygon points="{r}" fill="{shade(top_c, 0.5)}"/>')
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# snake eating the contribution graph
# --------------------------------------------------------------------------- #

def render_snake(days: list[dict], theme: str) -> str:
    weeks: list[list[dict]] = []
    cur: list[dict] = []
    first_wd = dt.date.fromisoformat(days[0]["date"]).weekday()
    pad = (first_wd + 1) % 7
    cur = [{"level": 0}] * pad
    for d in days:
        cur.append(d)
        if len(cur) == 7:
            weeks.append(cur)
            cur = []
    if cur:
        weeks.append(cur + [{"level": 0}] * (7 - len(cur)))

    greens = GREENS_DARK if theme == "dark" else GREENS_LIGHT
    snake_c = "#39d353" if theme == "dark" else "#1f883d"

    pitch, s = 15, 11
    pad_xy = 14
    W = len(weeks) * pitch + pad_xy * 2
    H = 7 * pitch + pad_xy * 2

    # boustrophedon traversal: down col 0, up col 1, ...
    order = []
    for i in range(len(weeks)):
        js = range(7) if i % 2 == 0 else range(6, -1, -1)
        for j in js:
            order.append((i, j))
    n = len(order)
    dur = max(8.0, n * 0.035)

    def xy(i, j):
        return (pad_xy + i * pitch + pitch / 2, pad_xy + j * pitch + pitch / 2)

    path = "M " + " L ".join(f"{int(xy(i, j)[0])} {int(xy(i, j)[1])}"
                             for i, j in order)

    parts = [svg_open(W, H, "snake eating the contribution graph")]
    # one shared path; the snake rides it via <mpath>
    parts.append(f"<defs><path id=\"snakepath\" d=\"{path}\"/></defs>")
    # cells; each winks out as the snake head passes (negative-delay trick:
    # one keyframes rule, per-cell phase shift), then fades back
    parts.append(
        "<style>.cell{animation:eat %.1fs linear infinite}"
        "@keyframes eat{0%%,94%%{opacity:1}96%%,98%%{opacity:0}100%%{opacity:1}}"
        "</style>" % dur)
    for k, (i, j) in enumerate(order):
        x = int(pad_xy + i * pitch + (pitch - s) / 2)
        y = int(pad_xy + j * pitch + (pitch - s) / 2)
        delay = (k / n - 0.96) * dur
        parts.append(
            f'<rect x="{x}" y="{y}" width="{s}" height="{s}" rx="3" '
            f'fill="{greens[weeks[i][j]["level"]]}" class="cell" '
            f'style="animation-delay:{delay:.2f}s"/>')
    # body segments trail the head via negative begin offsets
    for b in range(18, 0, -1):
        parts.append(
            f'<circle r="{6.2 - b * 0.08:.2f}" fill="{snake_c}" opacity="0.92">'
            f'<animateMotion dur="{dur:.1f}s" repeatCount="indefinite" '
            f'begin="-{b * dur / 70:.2f}s"><mpath href="#snakepath"/>'
            f"</animateMotion></circle>")
    # head
    parts.append(
        f'<circle r="7.6" fill="{snake_c}" stroke="{shade(snake_c, 0.6)}" '
        f'stroke-width="1.5"><animateMotion dur="{dur:.1f}s" '
        f'repeatCount="indefinite"><mpath href="#snakepath"/>'
        f"</animateMotion></circle>")
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# language mix bar
# --------------------------------------------------------------------------- #

def render_languages(totals: dict[str, int], theme: str) -> str:
    from cards import LANG_COLOR
    th = THEMES[theme]
    W, bar_w = 620, 572
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:5]
    grand = sum(totals.values()) or 1
    rows = [(lang, n / grand) for lang, n in top]
    H = 52 + len(rows) * 26 + 18

    parts = [svg_open(W, H, "most used languages")]
    parts.append(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="10" '
                 f'fill="{th["bg"]}" stroke="{th["border"]}"/>')
    parts.append(f'<text x="24" y="34" font-size="15" font-weight="600" '
                 f'fill="{th["title"]}">languages</text>')
    # stacked bar
    x, y0, bh = 24, 48, 12
    for lang, frac in rows:
        w = max(2, bar_w * frac)
        c = LANG_COLOR.get(lang, "#8b949e")
        parts.append(f'<rect x="{x:.1f}" y="{y0}" width="{w:.1f}" height="{bh}" '
                     f'fill="{c}"/>')
        x += w
    # legend
    y = y0 + bh + 26
    for lang, frac in rows:
        c = LANG_COLOR.get(lang, "#8b949e")
        parts.append(f'<circle cx="32" cy="{y - 5}" r="6" fill="{c}"/>')
        parts.append(f'<text x="46" y="{y}" font-size="13" fill="{th["text"]}">'
                     f'{lang}</text>')
        parts.append(f'<text x="{W - 24}" y="{y}" font-size="13" '
                     f'text-anchor="end" fill="{th["muted"]}">'
                     f'{frac * 100:.1f}%</text>')
        y += 26
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--user", required=True)
    p.add_argument("--out", type=Path, default=Path("assets"))
    p.add_argument("--projects", type=Path, default=Path("assets/projects.json"))
    args = p.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    print("fetching contributions…")
    days = fetch_contributions(args.user)
    total, current, longest = streaks(days)
    print(f"  {len(days)} days, {total} contributions, "
          f"streak {current} (longest {longest})")
    (out / "contrib.json").write_text(json.dumps(
        {"total": total, "current": current, "longest": longest}))

    print("writing metrics.isocalendar.svg")
    (out / "metrics.isocalendar.svg").write_text(render_isocalendar(days, total))
    print("writing snake SVGs")
    (out / "snake-dark.svg").write_text(render_snake(days, "dark"))
    (out / "snake.svg").write_text(render_snake(days, "light"))

    print("fetching languages…")
    langs = fetch_languages(args.user)
    for theme in ("dark", "light"):
        (out / f"metrics.languages-{theme}.svg").write_text(
            render_languages(langs, theme))
    print("writing metrics.languages-*.svg")

    here = Path(__file__).resolve().parent
    print("refreshing cards (cards.py)…")
    subprocess.run([sys.executable, str(here / "cards.py"), "--user", args.user,
                    "--out", str(out), "--projects", str(args.projects),
                    "--contrib-json", str(out / "contrib.json")], check=True)
    print("refreshing language radar (radar.py)…")
    subprocess.run([sys.executable, str(here / "radar.py"), "--github", args.user,
                    "-o", str(out / "radar-langs"), "--limit", "7", "--values",
                    "--curve", "0.4", "--skip-repos", args.user,
                    "--exclude", "shell,makefile,dockerfile,batchfile,procfile"],
                   check=True)
    print("done.")


if __name__ == "__main__":
    main()
