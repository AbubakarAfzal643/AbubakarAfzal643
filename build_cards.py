#!/usr/bin/env python3
"""Render the profile README cards (animated SVG) into cards/.

    python build_cards.py            animated cards  -> cards/
    STATIC=1 python build_cards.py   final frame, no animation -> cards-static/ + preview.html

Everything is plain CSS keyframes (SMIL is deliberately not used: a media query
cannot switch SMIL off, so prefers-reduced-motion would not be honoured).
Fonts are subset per card with pyftsubset and embedded as base64 WOFF.
Data comes from data/contributions.json (see scripts/fetch_contributions.py).
"""
from __future__ import annotations

import base64
import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = os.environ.get("STATIC") == "1"
OUT = ROOT / ("cards-static" if STATIC else "cards")
DATA_FILE = ROOT / "data" / "contributions.json"
FONT_DIR = ROOT / "fonts"

# --------------------------------------------------------------------------
# Edit these
# --------------------------------------------------------------------------
PROFILE = {
    "login": "AbubakarAfzal643",
    "name": "Abubakar Afzal",
    "tagline": "Software engineering undergrad focused on Salesforce CRM development.",
    "status": "building Salesforce-focused CRM solutions",
    "portrait": None,  # e.g. "assets/portrait.jpg" (square-ish image)
}

TILES = [  # key, label, handle shown, url, accent, icon
    ("linkedin", "LinkedIn", "abubakar-afzal", "https://linkedin.com/in/abubakar-afzal-214344287", "#91C9D6", "in"),
    ("email", "Email", "abubakarafzal643@gmail.com", "mailto:abubakarafzal643@gmail.com", "#6FAFC1", "mail"),
    ("instagram", "Instagram", "@abubakar.cpp", "https://instagram.com/abubakar.cpp", "#B0C9D1", "ig"),
]

FEATURED = [  # repo is "owner/name"; stats come from data/contributions.json when present
    {
        "repo": "QuantumLogicsLabs/DigitalLogicsStudio-Backend",
        "title": "Digital Logics Studio",
        "blurb": "Backend services for Digital Logic Design and COAL learning tools, including APIs "
                 "for interactive modules, circuit simulation, and a problems library.",
        "tags": ["APIs", "Simulation", "Digital Logic", "COAL"],
    },
    {
        "repo": "AbubakarAfzal643/AutoSphere_v2",
        "title": "AutoSphere v2",
        "blurb": "Automotive marketplace and service platform for vehicle parts, with separate "
                 "role-based interfaces for buyers and vendors.",
        "tags": ["MongoDB", "Express", "React", "Node.js"],
    },
    {
        "repo": "AbubakarAfzal643/mini-linkedin",
        "title": "Mini-LinkedIn",
        "blurb": "Social networking app with secure authentication, editable profiles and full "
                 "CRUD for user posts.",
        "tags": ["React", "Vite", "Appwrite", "Redux Toolkit", "Tailwind"],
    },
    {
        "repo": "AbubakarAfzal643/RESQ-frontend",
        "title": "ResQ Frontend",
        "blurb": "User-facing frontend for a disaster relief platform connecting victims, volunteers, "
                 "donors, and administrators.",
        "tags": ["React", "Tailwind", "Disaster Relief"],
    },
    {
        "repo": "AbubakarAfzal643/RESQ-backend",
        "title": "ResQ Backend",
        "blurb": "Backend services for a disaster relief platform supporting users, volunteers, donors, "
                 "and administrators.",
        "tags": ["Node.js", "Express", "MongoDB"],
    },
]

# Palette sampled from the deep teal and blue-gray accents in the GitHub avatar.
THEME = {
    "bg": "#071923",
    "surface": "#0B2631",
    "border": "#194657",
    "text": "#EAF2F4",
    "muted": "#9AB4BF",
    "brand": "#91C9D6",
    "empty": "#122F3B",
    "star": "#B0C9D1",
}
CHAR_W = 0.6  # JetBrains Mono advance, in em

FONT_FILES = {400: "JetBrainsMono-Regular.ttf", 800: "JetBrainsMono-ExtraBold.ttf"}
FONT_URL = "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/"

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
esc = lambda s: html.escape(str(s), quote=True)  # noqa: E731
tw = lambda s, size: len(s) * CHAR_W * size  # noqa: E731


def mix(a: str, b: str, t: float) -> str:
    """Blend colour a toward b by t (0..1)."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


def an(cls: str, delay: float, style: str = "") -> str:
    """class + staggered delay for an animated element (plain in STATIC mode)."""
    if STATIC:
        return f'class="{cls}"'
    return f'class="{cls}" style="animation-delay:{delay:.2f}s{";" + style if style else ""}"'


def draw_attrs(length: float, delay: float) -> str:
    """Stroke-draw animation using the real path length (no pathLength dependency)."""
    base = f"stroke-dasharray:{length:.1f}"
    if STATIC:
        return f'style="{base}"'
    return f'class="draw" style="{base};--L:{length:.1f};animation-delay:{delay:.2f}s"'


def short_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"


CSS_STRUCT = """
text{font-family:'JBM','JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.flow{stroke-dasharray:3 9}
.typed{clip-path:inset(0 0 0 0)}
"""

CSS_ANIM = """
.grow,.pop,.sheen{transform-box:fill-box}
.grow{transform-origin:50% 100%}
.pop{transform-origin:50% 50%}
.rise{animation:rise .7s cubic-bezier(.2,.7,.2,1) backwards}
.fade{animation:fade .7s ease-out backwards}
.draw{animation:draw .9s ease-out backwards}
.grow{animation:grow .8s cubic-bezier(.2,.7,.2,1) backwards}
.pop{animation:pop .4s ease-out backwards}
.sheen{animation:sheen 1.2s ease-in-out backwards}
.pulse{animation:pulse 2.4s ease-in-out infinite}
.breathe{animation:breathe 7s ease-in-out infinite}
.flow{animation:flow 1.2s linear infinite}
@keyframes rise{from{opacity:0;transform:translateY(8px)}}
@keyframes fade{from{opacity:0}}
@keyframes draw{from{stroke-dashoffset:var(--L)}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes pop{from{opacity:0;transform:scale(.4)}}
@keyframes sheen{to{transform:translateX(440px)}}
@keyframes pulse{50%{opacity:.3}}
@keyframes breathe{50%{opacity:.5}}
@keyframes flow{to{stroke-dashoffset:-12}}
@keyframes blink{50%{opacity:0}}
@keyframes type{from{clip-path:inset(0 100% 0 0)}}
"""

CSS_REDUCED = (
    "@media (prefers-reduced-motion:reduce){"
    "*,*::before,*::after{animation:none!important;transition:none!important}}"
)


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
def ensure_font(weight: int) -> Path | None:
    path = FONT_DIR / FONT_FILES[weight]
    if path.exists():
        return path
    try:
        FONT_DIR.mkdir(exist_ok=True)
        print(f"downloading {path.name} ...")
        urllib.request.urlretrieve(FONT_URL + path.name, path)
        return path
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not get {path.name} ({exc}); falling back to system monospace", file=sys.stderr)
        return None


def subset_b64(path: Path, chars: set[str]) -> str:
    text = "".join(sorted(chars | {" "}))
    exe = shutil.which("pyftsubset")
    cmd = [exe] if exe else [sys.executable, "-m", "fontTools.subset"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "s.woff"
        subprocess.run(
            cmd + [str(path), f"--text={text}", "--flavor=woff", f"--output-file={out}",
                   "--layout-features=", "--no-hinting", "--name-IDs=", "--notdef-outline"],
            check=True, capture_output=True,
        )
        return base64.b64encode(out.read_bytes()).decode()


# --------------------------------------------------------------------------
# Card base
# --------------------------------------------------------------------------
class Card:
    def __init__(self, name: str, w: int, h: int, delay: float, label: str):
        self.name, self.w, self.h, self.delay, self.label = name, w, h, delay, label
        self.defs: list[str] = []
        self.body: list[str] = []
        self.css = ""
        self.chars: dict[int, set[str]] = {400: set(), 800: set()}

    def d(self, off: float = 0.0) -> float:
        return self.delay + off

    def add(self, s: str) -> None:
        self.body.append(s)

    def text(self, x, y, s, size=13, weight=400, fill=None, anchor="start", extra="") -> None:
        self.chars[weight].update(s)
        self.add(
            f'<text x="{x:g}" y="{y:g}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill or THEME["text"]}" text-anchor="{anchor}" {extra}>{esc(s)}</text>'
        )

    def shell(self, rx: int = 18) -> None:
        self.defs.append(f'<clipPath id="clip"><rect width="{self.w}" height="{self.h}" rx="{rx}"/></clipPath>')
        self.add(
            f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="{rx}" '
            f'fill="{THEME["bg"]}" stroke="{THEME["border"]}"/>'
        )

    def render(self) -> str:
        fonts = ""
        for weight, chars in self.chars.items():
            if not chars:
                continue
            path = ensure_font(weight)
            if path:
                b64 = subset_b64(path, chars)
                fonts += (f"@font-face{{font-family:'JBM';font-weight:{weight};"
                          f"src:url(data:font/woff;base64,{b64}) format('woff')}}")
        css = fonts + CSS_STRUCT + self.css
        if not STATIC:
            css += CSS_ANIM + CSS_REDUCED
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" role="img" '
            f'aria-label="{esc(self.label)}"><title>{esc(self.label)}</title>'
            f"<style>{css}</style><defs>{''.join(self.defs)}</defs>{''.join(self.body)}</svg>"
        )


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def demo_days(end: date) -> list[dict]:
    import random
    rnd = random.Random(7)
    out = []
    for i in range(365):
        d = end - timedelta(days=364 - i)
        base = 0 if d.weekday() >= 5 and rnd.random() < 0.6 else rnd.choice([0, 0, 1, 2, 3, 5, 8, 13])
        if 110 < i < 150:
            base += rnd.choice([2, 4, 6])
        out.append({"date": d.isoformat(), "count": base})
    return out


def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    print(f"WARNING: {DATA_FILE} not found, using demo data (layout preview only)", file=sys.stderr)
    return {"login": PROFILE["login"], "generated": date.today().isoformat(),
            "days": demo_days(date.today()), "repos": {}}


def analyse(days: list[dict]) -> dict:
    counts = {date.fromisoformat(d["date"]): int(d["count"]) for d in days}
    end = max(counts)
    start = end - timedelta(days=364)
    window = [start + timedelta(i) for i in range(365)]
    series = [counts.get(d, 0) for d in window]

    cur, probe = 0, end
    if counts.get(probe, 0) == 0:
        probe -= timedelta(days=1)  # today may simply not have started yet
    while counts.get(probe, 0) > 0:
        cur += 1
        probe -= timedelta(days=1)
    best = run = 0
    for v in series:
        run = run + 1 if v > 0 else 0
        best = max(best, run)

    busiest_day = max(window, key=lambda d: (counts.get(d, 0), -d.toordinal()))

    months = []
    y, m = end.year, end.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    monthly = [sum(v for d, v in counts.items() if (d.year, d.month) == ym and start <= d <= end) for ym in months]

    return {
        "end": end, "start": start, "counts": counts, "window": window,
        "total": sum(series), "active": sum(1 for v in series if v > 0),
        "streak": cur, "longest": best,
        "busiest": (busiest_day, counts.get(busiest_day, 0)),
        "months": months, "monthly": monthly,
    }


# --------------------------------------------------------------------------
# Icons (drawn, so no glyph is needed from the font)
# --------------------------------------------------------------------------
def icon_star(x, y, s=14, fill=None):
    pts = []
    for i in range(10):
        r = s / 2 if i % 2 == 0 else s / 4.6
        a = -math.pi / 2 + i * math.pi / 5
        pts.append(f"{x + s / 2 + r * math.cos(a):.2f},{y + s / 2 + r * math.sin(a):.2f}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill or THEME["star"]}"/>'


def icon_fork(x, y, color):
    return (
        f'<g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round">'
        '<circle cx="3.5" cy="2.8" r="1.8"/><circle cx="10.5" cy="2.8" r="1.8"/><circle cx="7" cy="11.4" r="1.8"/>'
        '<path d="M3.5 4.6v1a1.8 1.8 0 0 0 1.8 1.8h3.4a1.8 1.8 0 0 0 1.8-1.8v-1M7 7.4v2.2"/></g>'
    )


def icon_repo(x, y, color):
    return (
        f'<g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round">'
        '<rect x="1" y="1" width="12" height="15" rx="2"/><path d="M1 12h12M5 12v4l2-1.4 2 1.4v-4"/></g>'
    )


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------
def card_hero(delay: float) -> Card:
    W, H, PAD = 830, 252, 48
    brand, muted, border = THEME["brand"], THEME["muted"], THEME["border"]
    c = Card("hero-salesforce", W, H, delay, f"{PROFILE['name']}: {PROFILE['tagline']}")
    c.shell(20)
    c.defs.append(
        f'<radialGradient id="glow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{brand}" stop-opacity=".22"/>'
        f'<stop offset="1" stop-color="{brand}" stop-opacity="0"/></radialGradient>'
        f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="{border}"/></pattern>'
    )
    c.add('<g clip-path="url(#clip)">')
    c.add(f'<rect width="{W}" height="{H}" fill="url(#dots)" opacity=".55"/>')
    c.add(f'<circle cx="705" cy="126" r="190" fill="url(#glow)" {an("breathe", c.d())}/>')
    c.add("</g>")

    c.text(PAD, 64, "> whoami", 13, 400, brand, extra=an("fade", c.d(0.1)))

    name_size = 46
    name_w = tw(PROFILE["name"], name_size)
    c.text(PAD, 124, PROFILE["name"], name_size, 800, THEME["text"], extra=an("rise", c.d(0.25)))
    c.add(f'<path d="M{PAD} 142H{PAD + name_w:.1f}" stroke="{brand}" stroke-width="3" '
          f'stroke-linecap="round" fill="none" {draw_attrs(name_w, c.d(0.7))}/>')

    # typed tagline with a cursor that travels with it
    tag = PROFILE["tagline"]
    avail = 575 - PAD
    size = min(16, avail / (len(tag) * CHAR_W))
    width = tw(tag, size)
    n = len(tag)
    t0, dur = c.d(1.0), n * 0.026
    typed_style = "" if STATIC else f'style="animation:type {dur:.2f}s steps({n},end) {t0:.2f}s backwards"'
    c.text(PAD, 186, tag, size, 400, THEME["text"], extra=f'class="typed" {typed_style}')
    cur_style = ""
    if not STATIC:
        c.css += f"@keyframes cur{{from{{transform:translateX(-{width:.1f}px)}}}}"
        cur_style = (f'style="animation:cur {dur:.2f}s steps({n},end) {t0:.2f}s backwards,'
                     f'blink 1s steps(1,end) {t0 + dur:.2f}s infinite"')
    c.add(f'<rect x="{PAD + width + 3:.1f}" y="{186 - size:.1f}" width="{size * 0.5:.1f}" height="{size * 1.2:.1f}" '
          f'fill="{brand}" {cur_style}/>')

    # status pill
    status = PROFILE["status"]
    pw = 28 + tw(status, 12) + 16
    py = 208
    c.add(f'<g {an("rise", c.d(1.0 + dur + 0.1))}>')
    c.add(f'<rect x="{PAD}" y="{py}" width="{pw:.1f}" height="26" rx="13" fill="{mix(THEME["bg"], brand, .08)}" stroke="{mix(THEME["bg"], brand, .3)}"/>')
    c.add(f'<circle cx="{PAD + 15}" cy="{py + 13}" r="4" fill="{brand}" {an("pulse", c.d(2))}/>')
    c.text(PAD + 28, py + 17, status, 12, 400, THEME["text"])
    c.add("</g>")

    # right-hand graphic: portrait if supplied, otherwise the Salesforce cloud mark
    portrait = PROFILE.get("portrait")
    if portrait and (ROOT / portrait).exists():
        p = ROOT / portrait
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode()
        c.defs.append('<clipPath id="pc"><circle cx="705" cy="126" r="72"/></clipPath>')
        c.add(f'<g {an("fade", c.d(0.4))}><image href="data:{mime};base64,{b64}" x="633" y="54" width="144" height="144" '
              f'preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)"/>'
              f'<circle cx="705" cy="126" r="73" fill="none" stroke="{brand}" stroke-width="2"/></g>')
    else:
        cloud = (
            "M661 175C647 178 635 169 633 156C621 151 616 138 621 126"
            "C625 115 636 108 648 109C649 94 660 82 675 80"
            "C687 77 699 82 706 91C719 83 735 86 743 98"
            "C757 96 769 106 772 119C783 128 783 144 775 154"
            "C768 164 756 168 744 165C736 177 721 182 707 177"
            "C695 189 677 190 666 180C664 178 662 177 661 175Z"
        )
        c.add(f'<g {an("fade", c.d(0.4))}>')
        c.add(f'<path d="{cloud}" fill="{mix(THEME["bg"], brand, .08)}" stroke="{brand}" '
              f'stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
        c.text(700, 140, "salesforce developer", 12, 800, brand, anchor="middle")
        c.add("</g>")
    return c


def card_tile(key, label, handle, accent, icon, delay) -> Card:
    W, H = 270, 122
    c = Card(f"tile-{key}", W, H, delay, f"{label}: {handle}")
    c.shell(16)
    c.defs.append(f'<clipPath id="tc"><rect width="{W}" height="{H}" rx="16"/></clipPath>')
    c.defs.append('<linearGradient id="sh" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                  '<stop offset=".5" stop-color="#fff" stop-opacity=".09"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    c.add(f'<g {an("rise", c.d())}>')
    c.add(f'<rect x="22" y="20" width="44" height="44" rx="12" fill="{mix(THEME["bg"], accent, .12)}" stroke="{mix(THEME["bg"], accent, .35)}"/>')
    s = f'fill="none" stroke="{accent}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
    if icon == "mail":
        c.add(f'<g transform="translate(33,31)" {s}><rect x="0" y="2" width="22" height="16" rx="3"/><path d="M1.5 4.5l9.5 7 9.5-7"/></g>')
    elif icon == "ig":
        c.add(f'<g transform="translate(33,31)" {s}><rect x="1" y="1" width="20" height="20" rx="6"/><circle cx="11" cy="11" r="4.6"/>'
              f'<circle cx="16.6" cy="5.4" r=".6" fill="{accent}"/></g>')
    else:
        c.text(44, 48, "in", 20, 800, accent, anchor="middle")
    c.text(22, 90, label, 17, 800, THEME["text"])
    c.text(22, 107, handle, 11, 400, THEME["muted"])
    c.add(f'<path d="M238 30l14-14M242 16h10v10" fill="none" stroke="{THEME["muted"]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>')
    c.add("</g>")
    c.add(f'<g clip-path="url(#tc)"><g transform="skewX(-20)"><rect x="-120" y="-10" width="60" height="140" fill="url(#sh)" {an("sheen", c.d(0.7))}/></g></g>')
    return c


def card_chart(stats: dict, delay: float) -> Card:
    W, H = 830, 310
    brand, muted, border = THEME["brand"], THEME["muted"], THEME["border"]
    c = Card("contributions-chart", W, H, delay,
             f"Contributions per month: {stats['total']:,} in the last year, current streak {stats['streak']} days")
    c.shell(20)
    c.defs.append(f'<linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{brand}"/>'
                  f'<stop offset="1" stop-color="{brand}" stop-opacity=".3"/></linearGradient>')
    c.text(40, 50, "Contributions per month", 17, 800, THEME["text"], extra=an("fade", c.d()))
    c.text(40, 71, f"{stats['total']:,} in the last 12 months", 12, 400, muted, extra=an("fade", c.d(0.1)))

    x0, x1, base, top = 84, 560, 252, 104
    monthly = stats["monthly"]
    peak = max(monthly) or 1
    p = 10 ** math.floor(math.log10(peak))
    ymax = next(m * p for m in (1, 2, 5, 10) if peak <= m * p)
    ymax = max(ymax, 1)
    for frac in (0.5, 1.0):
        y = base - (base - top) * frac
        c.add(f'<path d="M{x0 - 8} {y:.1f}H{x1}" stroke="{border}" stroke-dasharray="2 5" fill="none"/>')
        c.text(x0 - 14, y + 4, f"{int(ymax * frac):,}", 10, 400, muted, anchor="end")
    c.add(f'<path d="M{x0 - 8} {base}H{x1}" stroke="{border}" fill="none"/>')

    pitch = (x1 - x0) / 12
    bw = 26
    for i, (v, (y_, m_)) in enumerate(zip(monthly, stats["months"])):
        cx = x0 + pitch * i + pitch / 2
        h = max(2.0, v / ymax * (base - top)) if v else 2.0
        last = i == 11
        fill = "url(#bar)" if v else border
        dl = c.d(0.25 + i * 0.07)
        c.add(f'<rect x="{cx - bw / 2:.1f}" y="{base - h:.1f}" width="{bw}" height="{h:.1f}" rx="4" fill="{fill}" '
              f'{an("grow", dl)}/>')
        if v:
            c.text(cx, base - h - 7, f"{v:,}", 11, 800 if last else 400, brand if last else muted, anchor="middle",
                   extra=an("fade", dl + 0.5))
        c.text(cx, base + 20, date(y_, m_, 1).strftime("%b"), 11, 400, THEME["text"] if last else muted, anchor="middle")

    c.add(f'<path d="M590 96V268" stroke="{border}" fill="none"/>')
    bd, bc = stats["busiest"]
    days = lambda n: f"{n} day" + ("" if n == 1 else "s")  # noqa: E731
    blocks = [
        (days(stats["streak"]), "current streak", f"longest {days(stats['longest'])}"),
        (days(stats["active"]), "active in the last 365", None),
        (f"{bc:,}", f"busiest day, {short_date(bd)}", None),
    ]
    for j, (val, lab, sub) in enumerate(blocks):
        y = 116 + j * 74
        dl = c.d(0.7 + j * 0.2)
        c.text(622, y, val, 30, 800, brand, extra=an("rise", dl))
        c.text(622, y + 20, lab, 12, 400, THEME["text"], extra=an("fade", dl + 0.15))
        if sub:
            c.text(622, y + 36, sub, 11, 400, muted, extra=an("fade", dl + 0.25))
    return c


def card_repo(i: int, item: dict, repo_stats: dict, delay: float) -> Card:
    W, H = 830, 166
    brand, muted, border = THEME["brand"], THEME["muted"], THEME["border"]
    owner, name = item["repo"].split("/")
    c = Card(f"repo-{i + 1}", W, H, delay, f"{item['title']}: {item['blurb']}")
    c.shell(18)
    c.defs.append(f'<clipPath id="rc"><rect width="{W}" height="{H}" rx="18"/></clipPath>')
    c.add(f'<g clip-path="url(#rc)"><rect x="0" y="0" width="5" height="{H}" fill="{brand}" {an("grow", c.d())}/></g>')
    c.add(f'<g {an("fade", c.d(0.1))}>{icon_repo(40, 26, brand)}</g>')
    c.text(66, 40, item["title"], 19, 800, brand, extra=an("rise", c.d(0.1)))
    c.text(66, 60, f"{owner}/{name}", 12, 400, muted, extra=an("fade", c.d(0.25)))

    # stats, right aligned (only when the data file has them)
    x = W - 40
    items = []
    if repo_stats:
        items = [("forks", repo_stats.get("forks")), ("stars", repo_stats.get("stars"))]
        for kind, val in items:
            if val is None:
                continue
            s = f"{val:,}"
            c.text(x, 40, s, 13, 800, THEME["text"], anchor="end", extra=an("fade", c.d(0.3)))
            x -= tw(s, 13) + 6
            c.add(f'<g {an("fade", c.d(0.3))}>' + (icon_star(x - 14, 29, 14) if kind == "stars" else icon_fork(x - 14, 29, muted)) + "</g>")
            x -= 28
        lang = repo_stats.get("language")
        if lang:
            lc = repo_stats.get("language_color") or brand
            c.text(x, 40, lang, 12, 400, muted, anchor="end", extra=an("fade", c.d(0.3)))
            x -= tw(lang, 12) + 12
            c.add(f'<circle cx="{x:.1f}" cy="36" r="5" fill="{lc}" {an("fade", c.d(0.3))}/>')

    lines = textwrap.wrap(item["blurb"], width=92)[:2]
    for k, ln in enumerate(lines):
        c.text(40, 94 + k * 19, ln, 13, 400, THEME["text"], extra=an("fade", c.d(0.35 + k * 0.1)))

    px = 40
    for k, tag in enumerate(item["tags"]):
        w = tw(tag, 11) + 22
        dl = c.d(0.55 + k * 0.07)
        c.add(f'<g {an("rise", dl)}><rect x="{px:.1f}" y="128" width="{w:.1f}" height="24" rx="12" '
              f'fill="{mix(THEME["bg"], brand, .06)}" stroke="{border}"/></g>')
        c.text(px + w / 2, 144, tag, 11, 400, muted, anchor="middle", extra=an("fade", dl))
        px += w + 8
    return c


def card_graph(stats: dict, delay: float) -> Card:
    W, H = 830, 232
    brand, muted = THEME["brand"], THEME["muted"]
    c = Card("contribution-graph", W, H, delay, f"Contribution graph: {stats['total']:,} contributions in the last year")
    c.shell(20)
    c.text(40, 46, "Contribution graph", 17, 800, THEME["text"], extra=an("fade", c.d()))
    c.text(40, 67, f"{stats['total']:,} contributions in the last year", 12, 400, muted, extra=an("fade", c.d(0.1)))

    levels = [THEME["empty"]] + [mix(THEME["bg"], brand, t) for t in (0.3, 0.55, 0.78, 1.0)]
    nz = sorted(v for v in stats["counts"].values() if v > 0)
    q = [nz[int(len(nz) * f)] if nz else 1 for f in (0.25, 0.5, 0.75)]

    def level(v: int) -> int:
        if v <= 0:
            return 0
        return 1 + sum(v > t for t in q) if v > q[0] else 1

    # legend
    lx = W - 40 - 5 * 14 - tw("More", 10) - 8
    c.text(lx - 8, 67, "Less", 10, 400, muted, anchor="end")
    for k, col in enumerate(levels):
        c.add(f'<rect x="{lx + k * 14}" y="58" width="11" height="11" rx="3" fill="{col}"/>')
    c.text(lx + 5 * 14 + 4, 67, "More", 10, 400, muted)

    gx, gy, pitch = 52, 98, 14
    first = stats["start"] - timedelta(days=(stats["start"].weekday() + 1) % 7)  # back to Sunday
    cols = ((stats["end"] - first).days // 7) + 1
    last_month = None
    rules, month_marks = [], []
    for col in range(cols):
        wk = first + timedelta(weeks=col)
        mid = wk + timedelta(days=3)
        if mid.month != last_month and col <= cols - 3:
            month_marks.append((col, mid.strftime("%b")))
        last_month = mid.month
        rules.append(f".w{col}{{animation-delay:{c.d(0.2 + col * 0.022):.2f}s}}")
        for row in range(7):
            d = wk + timedelta(days=row)
            if d < stats["start"] or d > stats["end"]:
                continue
            v = stats["counts"].get(d, 0)
            c.add(f'<rect class="pop w{col}" x="{gx + col * pitch}" y="{gy + row * pitch}" width="11" height="11" rx="3" '
                  f'fill="{levels[level(v)]}"/>')
    if len(month_marks) > 1 and month_marks[1][0] - month_marks[0][0] < 3:
        month_marks.pop(0)  # first label would collide with the next one
    for col, lab in month_marks:
        c.text(gx + col * pitch, gy - 10, lab, 10, 400, muted)
    if not STATIC:
        c.css += "".join(rules)
    for row, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        c.text(gx - 8, gy + row * pitch + 9, lab, 10, 400, muted, anchor="end")
    return c


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def write_preview(names: list[str]) -> None:
    hero = next(n for n in names if n == "hero-salesforce")
    tiles = "".join(f'<img src="{n}.svg" style="width:32.4%;vertical-align:top;margin:0 .3%">' for n in names
                    if n.startswith("tile-"))
    rest = "".join(f'<img src="{n}.svg" style="width:100%;display:block;margin:12px 0">' for n in names
                   if not n.startswith("tile-") and n != hero)
    page = (
        "<!doctype html><meta charset=utf-8><title>README preview</title>"
        "<body style='margin:0;background:#0d1117;display:flex;justify-content:center'>"
        "<div style='width:830px;padding:24px 0;text-align:center'>"
        f"<img src='{hero}.svg' style='width:100%;display:block;margin:0 0 16px'>"
        f"<div>{tiles}</div>{rest}</div></body>"
    )
    (OUT / "preview.html").write_text(page, encoding="utf-8")


def main() -> None:
    data = load_data()
    stats = analyse(data["days"])
    repo_stats = data.get("repos", {})

    t = {"hero": 0.0, "tiles": 1.9, "chart": 2.7, "repos": 3.7, "step": 0.5}
    cards = [card_hero(t["hero"])]
    for i, (key, label, handle, _url, accent, icon) in enumerate(TILES):
        cards.append(card_tile(key, label, handle, accent, icon, t["tiles"] + i * 0.15))
    cards.append(card_chart(stats, t["chart"]))
    for i, item in enumerate(FEATURED):
        cards.append(card_repo(i, item, repo_stats.get(item["repo"], {}), t["repos"] + i * t["step"]))
    cards.append(card_graph(stats, t["repos"] + len(FEATURED) * t["step"] + 0.2))

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for c in cards:
        svg = c.render()
        (OUT / f"{c.name}.svg").write_text(svg, encoding="utf-8")
        print(f"{OUT.name}/{c.name}.svg  {len(svg) / 1024:.1f} KB")
    if STATIC:
        write_preview([c.name for c in cards])
        print(f"final-frame preview: {OUT / 'preview.html'}")


if __name__ == "__main__":
    main()
