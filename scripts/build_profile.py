#!/usr/bin/env python3
"""Builds README.md and assets/*.svg (light and dark variants).

Needs fonttools and brotli:  pip install fonttools brotli
Run from anywhere:            python3 scripts/build_profile.py
Check committed output:       python3 scripts/build_profile.py --check   (exits 1 if a rebuild would change anything)
"""

import base64
import io
import math
import sys
from html import escape
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONT_DIR = Path(__file__).resolve().parent / "fonts"
FALLBACK = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

THEMES = {
    "light": dict(
        ink="#231A16", muted="#6E5D55", primary="#A23F16", on_primary="#FFFFFF",
        sec="#5A55A8", ter="#1C6B55", yel="#8A6B00",
        glass_ink="#1C1B22", tint="#FFFFFF", sheen=0.45, card_frost=0.55,
        base=("#FFE3D6", "#E4E0FF"), blobs=["#FF8A65", "#7C6CFF", "#3FD1A8", "#FFC23D", "#FF6FAE"],
    ),
    "dark": dict(
        ink="#F0DFD8", muted="#B9A79F", primary="#FFB59B", on_primary="#5C1900",
        sec="#C3C0FF", ter="#8FD5BD", yel="#E9C349",
        glass_ink="#FFFFFF", tint="#0B0B14", sheen=0.22, card_frost=0.45,
        base=("#24122E", "#0E1B33"), blobs=["#D9481C", "#5B4BDB", "#0F9D7A", "#C79100", "#C2367A"],
    ),
}
GLASS_TINT = 0.28


class Font:
    WEIGHT = {"display": 800, "bold": 700, "text": 400}
    FILE = {"display": "Display", "bold": "Bold", "text": "Text"}

    def __init__(self, key):
        self.key = key
        self.path = FONT_DIR / f"BricolageGrotesque-{self.FILE[key]}.ttf"
        tt = TTFont(self.path)
        self.cmap = tt.getBestCmap()
        self.adv = {g: tt["hmtx"][g][0] for g in tt.getGlyphOrder()}
        self.upm = tt["head"].unitsPerEm
        self._cache = {}

    def width(self, s, size, spacing=0.0):
        units = sum(self.adv[self.cmap.get(ord(c), ".notdef")] for c in s)
        return units * size / self.upm + spacing * max(len(s) - 1, 0)

    def face(self, chars):
        key = "".join(sorted(set(chars)))
        if key not in self._cache:
            opts = Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga", "calt"]
            opts.desubroutinize = True
            # Without recalcTimestamp=False every save stamps a new head.modified, so rebuilds never match.
            tt = TTFont(self.path, recalcTimestamp=False)
            sub = Subsetter(opts)
            sub.populate(text=key)
            sub.subset(tt)
            buf = io.BytesIO()
            tt.flavor = "woff2"
            tt.save(buf)
            self._cache[key] = base64.b64encode(buf.getvalue()).decode()
        return (
            f"@font-face{{font-family:bg-{self.key};font-weight:{self.WEIGHT[self.key]};"
            f"src:url(data:font/woff2;base64,{self._cache[key]}) format('woff2')}}"
        )


FONTS = {k: Font(k) for k in Font.WEIGHT}


def wrap(s, font, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and FONTS[font].width(trial, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines


class Svg:
    # `prefix` keeps generated ids and animation names unique when one canvas is built inside another.
    def __init__(self, w, h, label, prefix=""):
        self.w, self.h, self.label, self.prefix = w, h, label, prefix
        self.parts, self.defs, self.css = [], [], []
        self.used = {k: set() for k in FONTS}
        self._ids = 0

    def uid(self, kind):
        self._ids += 1
        return f"{self.prefix}{kind}{self._ids}"

    def text(self, x, y, s, font, size, fill, anchor="start", spacing=0.0, opacity=1.0, max_w=None):
        if max_w is not None:
            actual = FONTS[font].width(s, size, spacing)
            if actual > max_w + 0.5:
                raise ValueError(f"{s!r} is {actual:.0f}px wide, only {max_w:.0f}px available")
        missing = {c for c in s if ord(c) not in FONTS[font].cmap}
        if missing:
            raise ValueError(f"{font} font has no glyph for {''.join(sorted(missing))!r} in {s!r}")
        self.used[font].update(s)
        op = f' opacity="{opacity}"' if opacity != 1 else ""
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="bg-{font},{FALLBACK}" font-weight="{Font.WEIGHT[font]}" '
            f'font-size="{size}" fill="{fill}" text-anchor="{anchor}"{ls}{op}>{escape(s)}</text>'
        )

    def add(self, s):
        self.parts.append(s)

    def render(self):
        faces = "".join(FONTS[k].face(chars) for k, chars in self.used.items() if chars)
        css = faces + "".join(self.css) + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
            f'role="img" aria-label="{escape(self.label)}"><title>{escape(self.label)}</title>'
            f"<defs>{''.join(self.defs)}</defs><style>{css}</style>{''.join(self.parts)}</svg>\n"
        )


# ---- Material 3 Expressive-style shapes: polar curves sampled with a fixed point count so any two can morph.

N_POINTS = 144


def polar(cx, cy, r, fn):
    pts = []
    for i in range(N_POINTS):
        t = 2 * math.pi * i / N_POINTS
        rr = r * fn(t)
        pts.append(f"{cx + rr * math.cos(t):.1f} {cy + rr * math.sin(t):.1f}")
    return "M" + " L".join(pts) + " Z"


SHAPES = {
    "cookie9": lambda t: 1 + 0.07 * math.cos(9 * t),
    "cookie12": lambda t: 1 + 0.05 * math.cos(12 * t),
    "cookie4": lambda t: 1 + 0.12 * math.cos(4 * t),
    "flower": lambda t: 1 + 0.16 * math.cos(6 * t),
    "squircle": lambda t: (abs(math.cos(t)) ** 4 + abs(math.sin(t)) ** 4) ** -0.25 * 0.92,
    "clover": lambda t: 0.78 + 0.22 * abs(math.cos(2 * t)) ** 0.6,
}


def shape(svg, cx, cy, r, name, fill, opacity=1.0, morph=None, spin=None):
    d = polar(cx, cy, r, SHAPES[name])
    anim = ""
    if morph:
        seq = [d] + [polar(cx, cy, r, SHAPES[m]) for m in morph] + [d]
        n = len(seq) - 1
        key_times = ";".join(f"{i / n:.3f}" for i in range(n + 1))
        splines = ";".join(["0.6 0 0.2 1"] * n)
        anim = (
            f'<animate attributeName="d" dur="{3.2 * n:.1f}s" repeatCount="indefinite" values="{";".join(seq)}" '
            f'keyTimes="{key_times}" calcMode="spline" keySplines="{splines}"/>'
        )
    cls = ""
    if spin:
        name_ = svg.uid("spin")
        svg.css.append(
            f".{name_}{{transform-origin:{cx}px {cy}px;animation:{name_} {abs(spin)}s linear infinite}}"
            f"@keyframes {name_}{{to{{transform:rotate({360 if spin > 0 else -360}deg)}}}}"
        )
        cls = f' class="{name_}"'
    op = f' opacity="{opacity}"' if opacity != 1 else ""
    svg.add(f'<g{cls}><path d="{d}" fill="{fill}"{op}>{anim}</path></g>')


# ---- Liquid Glass: frosted copies of the wallpaper, clipped to each panel, with a tint, sheen and rim light.

def glass_defs(svg, p):
    svg.defs.append(
        '<filter id="frost" x="-10%" y="-10%" width="120%" height="120%">'
        '<feGaussianBlur stdDeviation="9"/><feColorMatrix type="saturate" values="1.5"/></filter>'
        '<filter id="gshadow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7"/></filter>'
        '<linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".95"/>'
        '<stop offset=".45" stop-color="#fff" stop-opacity=".12"/><stop offset="1" stop-color="#fff" stop-opacity=".6"/></linearGradient>'
        f'<linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="{p["sheen"]}"/>'
        '<stop offset=".5" stop-color="#fff" stop-opacity="0"/></linearGradient>'
    )


def glass(svg, x, y, w, h, r, src, p, frost=0.0):
    cid = svg.uid("gc")
    svg.defs.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/></clipPath>')
    svg.add(f'<rect x="{x}" y="{y + 6}" width="{w}" height="{h}" rx="{r}" fill="#000" opacity=".16" filter="url(#gshadow)"/>')
    svg.add(f'<g clip-path="url(#{cid})"><use href="#{src}" filter="url(#frost)"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{p["tint"]}" opacity="{GLASS_TINT + frost:.2f}"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#sheen)"/></g>')
    svg.add(f'<rect x="{x + .6}" y="{y + .6}" width="{w - 1.2}" height="{h - 1.2}" rx="{r}" fill="none" stroke="url(#rim)" stroke-width="1.3"/>')


def wallpaper(svg, wid, x, y, w, h, r, p, seed):
    gid, cid = svg.uid("wg"), svg.uid("wc")
    svg.defs.append(
        f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p["base"][0]}"/>'
        f'<stop offset="1" stop-color="{p["base"][1]}"/></linearGradient>'
        '<filter id="soft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="6"/></filter>'
        f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/></clipPath>'
    )
    blobs = Svg(1, 1, "", prefix=f"{wid}-")
    spots = [(.18, .22, .34, "cookie9", "flower"), (.85, .18, .30, "flower", "squircle"),
             (.70, .62, .40, "squircle", "cookie4"), (.12, .80, .32, "clover", "cookie9"),
             (.48, .40, .22, "cookie12", "clover")]
    for i, (fx, fy, fr, shp, morph) in enumerate(spots):
        shape(blobs, x + w * fx, y + h * fy, min(w, h) * fr, shp, p["blobs"][(i + seed) % 5],
              morph=[morph], spin=(50 + i * 7) * (-1) ** i)
    svg.css.extend(blobs.css)
    svg.defs.append(f'<g id="{wid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="url(#{gid})"/>'
                    f'<g filter="url(#soft)">{"".join(blobs.parts)}</g></g>')
    svg.add(f'<g clip-path="url(#{cid})"><use href="#{wid}"/></g>')


# ---- Hero: a glass phone with glass pills orbiting it over morphing Material shapes

ORBIT = [("Android", "primary"), ("iOS", "sec"), ("Performance", "ter"), ("On-device ML", "yel"),
         ("AR & spatial", "primary"), ("AI-native", "sec")]
HERO_ALT = ("Ankit Verma. Android and iOS engineer. Mobile first, curious about everything else. "
            "Orbiting: " + ", ".join(label for label, _ in ORBIT) + ".")


def pill_layer(svg, ell, p, dur, clip=None):
    if clip:
        svg.add(f'<g clip-path="url(#{clip})">')
    for i, (label, accent) in enumerate(ORBIT):
        tw = FONTS["bold"].width(label, 14) + 34
        motion = f'<animateMotion dur="{dur}s" repeatCount="indefinite" begin="-{i * dur / len(ORBIT):.1f}s" path="{ell}"/>'
        rect = f'x="{-tw / 2:.1f}" y="-18" width="{tw:.1f}" height="36" rx="18"'
        cid = svg.uid("oc")
        svg.defs.append(f'<clipPath id="{cid}"><rect {rect}>{motion}</rect></clipPath>')
        svg.add(f'<g><rect x="{-tw / 2:.1f}" y="-14" width="{tw:.1f}" height="36" rx="18" fill="#000" opacity=".16" filter="url(#gshadow)"/>{motion}</g>')
        svg.add(f'<g clip-path="url(#{cid})"><use href="#wallHero" filter="url(#frost)"/></g>')
        svg.used["bold"].update(label)
        svg.add(f'<g><rect {rect} fill="{p["tint"]}" opacity="{GLASS_TINT}"/><rect {rect} fill="url(#sheen)"/>'
                f'<rect x="{-tw / 2 + .6:.1f}" y="-17.4" width="{tw - 1.2:.1f}" height="34.8" rx="17.4" fill="none" stroke="url(#rim)" stroke-width="1.3"/>'
                f'<circle cx="{-tw / 2 + 16:.1f}" cy="0" r="4.5" fill="{p[accent]}"/>'
                f'<text x="7" y="5" text-anchor="middle" font-family="bg-bold,{FALLBACK}" font-weight="700" font-size="14" '
                f'fill="{p["glass_ink"]}">{escape(label)}</text>{motion}</g>')
    if clip:
        svg.add("</g>")


def hero(p):
    W, H, stage_h = 840, 610, 460
    svg = Svg(W, H, HERO_ALT)
    glass_defs(svg, p)
    wallpaper(svg, "wallHero", 0, 0, W, stage_h, 36, p, seed=2)
    cx, cy, rx, ry = W / 2, 228, 330, 112
    ell = f"M{cx - rx} {cy} A{rx} {ry} 0 1 1 {cx + rx} {cy} A{rx} {ry} 0 1 1 {cx - rx} {cy}"
    svg.add(f'<path d="{ell}" fill="none" stroke="#fff" stroke-opacity=".55" stroke-dasharray="3 7"/>')
    dur = 30
    # Drawn twice: the phone hides the far side of the orbit, and only the near (lower) half is redrawn on top.
    pill_layer(svg, ell, p, dur)
    pw, ph = 168, 320
    glass(svg, cx - pw / 2, cy - ph / 2, pw, ph, 40, "wallHero", p)
    shape(svg, cx, cy - 6, 50, "cookie9", p["primary"], morph=["flower", "squircle", "clover"], spin=40)
    svg.text(cx, cy + 8, "AV", "display", 30, p["on_primary"], anchor="middle")
    near = svg.uid("near")
    svg.defs.append(f'<clipPath id="{near}"><rect x="0" y="{cy}" width="{W}" height="{stage_h - cy}"/></clipPath>')
    pill_layer(svg, ell, p, dur, clip=near)
    svg.text(cx, 532, "Ankit Verma", "display", 60, p["ink"], anchor="middle", spacing=-1.5)
    svg.text(cx, 572, "Android & iOS engineer. Mobile first, curious about everything else.",
             "text", 18, p["muted"], anchor="middle", max_w=W)
    return svg


# ---- Spotlight cards (one image each, so each links to its project)

SPOTS = [
    ("miraro", "Miraro", "SHIPPED · PLAY STORE", "https://miraro.zettamask.com", 0,
     "A privacy-first gallery I designed and shipped end to end. Hide and share the photos you choose without exposing the whole device."),
    ("android-docs-mcp", "android-docs-mcp", "OPEN SOURCE · AI TOOLING", "https://github.com/ankit-verma-209171/android-docs-mcp", 3,
     "Gives AI coding agents direct access to developer.android.com docs, API references and release notes. My most-starred repo."),
]


def spot(p, name, tag, desc, seed):
    W, H = 414, 210
    svg = Svg(W, H, f"{name}. {tag}. {desc}")
    glass_defs(svg, p)
    wallpaper(svg, "wallSpot", 0, 0, W, H, 28, p, seed)
    glass(svg, 12, 12, W - 24, H - 24, 22, "wallSpot", p, frost=p["card_frost"])
    ink = p["glass_ink"]
    svg.text(32, 44, tag, "bold", 11, ink, spacing=1.4, opacity=0.75)
    svg.text(32, 82, name, "display", 28, ink, spacing=-0.5, max_w=320)
    lines = wrap(desc, "text", 14.5, W - 64)
    if len(lines) > 4:
        raise ValueError(f"{name}: description needs {len(lines)} lines, the card fits 4")
    for i, line in enumerate(lines):
        svg.text(32, 110 + i * 20, line, "text", 14.5, ink, opacity=0.9)
    arrow_ink = "#1C1B22" if ink == "#FFFFFF" else "#FFFFFF"
    svg.add(f'<circle cx="{W - 46}" cy="44" r="16" fill="{ink}" opacity=".9"/>'
            f'<path d="M{W - 51} 49 L{W - 41} 39 M{W - 48} 39 H{W - 41} V46" stroke="{arrow_ink}" '
            f'stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    return svg


# ---- Agent loop: the steps I run with AI agents, lit in turn as a dot travels the track

LOOP = ["Idea", "Explore", "Context", "Plan", "Build", "Lint", "Test", "Run", "Verify", "Review"]
LOOP_TOOLS = "Claude Code · Codex · Copilot"
LOOP_KIT = "skills · rules · agents · MCP · prompts · hooks · guardrails"
LOOP_ALT = ("The loop I run with AI agents: " + ", ".join(LOOP) + ". Tools: " + LOOP_TOOLS.replace(" · ", ", ")
            + ". Built on " + LOOP_KIT.replace(" · ", ", ") + ".")


def loop(p):
    W, H, dur = 840, 300, 20
    svg = Svg(W, H, LOOP_ALT)
    glass_defs(svg, p)
    wallpaper(svg, "wallLoop", 0, 0, W, H, 32, p, seed=1)
    glass(svg, 12, 12, W - 24, H - 24, 26, "wallLoop", p, frost=p["card_frost"])
    x0, x1, y0, y1 = 160, 680, 70, 230
    r = (y1 - y0) / 2
    straight, arc = x1 - x0, math.pi * r
    perim = 2 * straight + 2 * arc
    track = f"M{x0} {y0} H{x1} A{r} {r} 0 0 1 {x1} {y1} H{x0} A{r} {r} 0 0 1 {x0} {y0} Z"

    def at(d):
        d %= perim
        if d < straight:
            return x0 + d, y0
        d -= straight
        if d < arc:
            a = d / r - math.pi / 2
            return x1 + r * math.cos(a), y0 + r + r * math.sin(a)
        d -= arc
        if d < straight:
            return x1 - d, y1
        a = (d - straight) / r + math.pi / 2
        return x0 + r * math.cos(a), y0 + r + r * math.sin(a)

    ink = p["glass_ink"]
    svg.add(f'<path d="{track}" fill="none" stroke="{ink}" stroke-opacity=".22" stroke-width="2" stroke-dasharray="2 6" stroke-linecap="round"/>')
    step = perim / len(LOOP)
    # Four gaps before the right end's midpoint, so four pills sit on each straight and one caps each end.
    start = straight + arc / 2 - 4 * step
    for k, label in enumerate(LOOP):
        d = start + k * step
        cx, cy = at(d)
        tw = FONTS["bold"].width(label, 14) + 30
        rect = f'x="{cx - tw / 2:.1f}" y="{cy - 16:.1f}" width="{tw:.1f}" height="32" rx="16"'
        begin = d / perim * dur - 0.4
        svg.add(f'<rect {rect} fill="{p["tint"]}" opacity=".62"/>'
                f'<rect {rect} fill="{p["primary"]}" opacity="0"><animate attributeName="opacity" values="0;.42;0;0" '
                f'keyTimes="0;.04;.16;1" dur="{dur}s" begin="{begin:.2f}s" repeatCount="indefinite"/></rect>'
                f'<rect x="{cx - tw / 2 + .6:.1f}" y="{cy - 15.4:.1f}" width="{tw - 1.2:.1f}" height="30.8" rx="15.4" fill="none" stroke="url(#rim)" stroke-width="1.2"/>')
        svg.text(cx, cy + 5, label, "bold", 14, ink, anchor="middle")
    svg.add(f'<g><circle r="11" fill="{p["primary"]}" opacity=".28" filter="url(#soft)"/>'
            f'<circle r="5.5" fill="{p["primary"]}" stroke="#fff" stroke-width="2"/>'
            f'<animateMotion dur="{dur}s" repeatCount="indefinite" path="{track}"/></g>')
    mid = W / 2
    svg.text(mid, 146, LOOP_TOOLS, "bold", 16, ink, anchor="middle", opacity=0.9, max_w=360)
    svg.text(mid, 170, LOOP_KIT, "text", 12.5, ink, anchor="middle", opacity=0.7, max_w=380)
    return svg


# ---- README

def picture(name, alt, width="100%", href=None):
    img = (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
           f'<img src="assets/{name}-light.svg" alt="{escape(alt)}" width="{width}"></picture>')
    return f'<a href="{href}">{img}</a>' if href else img


README = """<!-- Generated by scripts/build_profile.py. Edit the script, then run it. -->

@HERO@

Throw me at anything: a new platform, a legacy codebase, a bug nobody can pin down. I start with a plan, work the problem down to its cause, and build something that stays stable. Mostly that means Android and iOS apps, which I've been building at [Simform](https://www.simform.com/) since 2023.

### What I've been doing

- **Owning a codebase.** When a teammate left, I stepped up to own a production Android codebase on a two-person team, handling both maintenance and new features. Teammates come to me when they're stuck on something technical.
- **From scratch to MVP.** I built a health-scanning Android app from scratch in two months: Jetpack Compose, real-time camera scanning with CameraX, and on-device ML with TensorFlow Lite. On another product, I was part of a 30-day push that took an MVP to the Play Store on deadline.
- **Migrations and clean-ups.** As the only developer, I brought a large legacy privacy browser up to Android 15 and 16 KB page sizes, resolving 500+ issues (the story is below). On a View-based social app for anime fans, I fixed 70+ issues in two months across stories, reels and AI chat, bringing it level with its iOS version while helping build new features.
- **Both platforms.** Kotlin and Compose day to day, plus production iOS work in Swift, SwiftUI and UIKit, including migrating complex UIKit table and collection screens to SwiftUI.
- **Testing and performance.** I introduced unit testing on a production app: wrote 500+ tests, updated 800+, and added them to the PR pipeline, where they guarded against regressions during large upgrades. In my own app, Baseline Profiles cut startup from about 1 s to 0.4 s.
- **Working across teams.** I get Product, Design, Backend and iOS aligned on missing user journeys and edge cases before development starts, so there's less rework. I'm mentoring a new teammate, and I've run sessions on AI on iOS and AR on Android.

### How I work with AI

Claude Code, Codex and Copilot are part of my daily work. This is the loop I run with them:

@LOOP@

- **Features, start to finish.** Agents do much of the writing; I own the plan, the context and the review.
- **Debugging.** Agents help me read unfamiliar code and test ideas quickly.
- **The setup around them.** Skills, rules, prompts, MCP servers, hooks and guardrails, tuned so agents follow the codebase's conventions. I build on Matt Pocock's skills and pstack.
- **Migrations.** A full app redesign, carried through the codebase with agents.
- **Sessions.** I've run sessions on AI-native engineering: the change in mindset, and running work in parallel.

### Problems I've worked through

<details open>
<summary><b>A legacy Mozilla-based privacy browser had to run on Android 15</b>, and I was the only developer on it</summary>

- **Starting point:** a very large, outdated codebase built on Mozilla's Android libraries, with a Redux-style architecture and a mix of Views and Compose.
- **What it took:**
  - following Mozilla's code as it moved from several repos into a monorepo, across two GitHub homes, and finally into mozilla-central
  - mapping Mozilla libraries and plugins that had broken or been removed to their newer replacements, along with the namespace, resource and string moves that came with them
  - porting the app to the upstream changes it needed to run on Android 15
  - recompiling an unmaintained third-party native library for 16 KB page sizes
  - improving the proxy handling, and the experience of switching between normal and proxy modes
- **The constraint:** modernise all of it without changing the default behaviour users got from those libraries.
- **Result:** 500+ issues resolved, and the app running on Android 15 with 16 KB page support.

</details>

<details>
<summary><b>An iOS app crashed and lost data</b> when users switched between several forms</summary>

- **Cause:** strong reference cycles in table view cells, plus incorrect image-loading behaviour.
- **Fix:** broke the reference cycles and corrected the image loading, diagnosed with Xcode Instruments. That ended the crash and the data loss it caused.

</details>

<details>
<summary><b>Recorded audio and video arrived corrupted or cut short</b> on unreliable networks (iOS)</summary>

- **Cause:** problems in three places: the recording configuration, the upload handling, and mismatched encoding.
- **Fix:** corrected all three, which resolved the corruption and made uploads more reliable.

</details>

<details>
<summary><b>Real-time camera scanning hit performance and memory bottlenecks</b> in the on-device ML pipeline (Android)</summary>

- **Cause:** performance and memory bottlenecks in the CameraX + TensorFlow Lite pipeline: object lifecycles and unnecessary intermediate computations.
- **Fix:** optimised the object lifecycles and removed those computations, which improved runtime stability during real-time scanning.

</details>

<details>
<summary><b>Linked dropdowns swapped their values</b> inside nested, server-driven forms (iOS)</summary>

- **Cause:** the way the form fields were generated let state from one subform leak into another.
- **Fix:** isolated updates to the active subform, so each dropdown keeps its own value.

</details>

<details>
<summary><b>App Links stopped verifying</b> during a domain migration (Android)</summary>

- **Cause:** Android's App Links verification failed after the move to a new domain.
- **Fix:** traced it to the root cause, documented it, and worked with the relevant teams to put the fix in place.

</details>

<details>
<summary><b>Deferred deep links worked on one phone but not another</b> (Android)</summary>

- **Cause:** the device and the app interpreted the user agent differently.
- **Fix:** tracked the mismatch down together with the backend team.

</details>

### Shipped and open source

<p>
@SPOTS@
</p>

| Project | What it shows |
| :--- | :--- |
| [**AR Treasure Hunt**](https://github.com/SimformSolutionsPvtLtd/SS-ARTreasureHunt) | Geospatial AR: 3D content anchored to real-world coordinates with ARCore and AR Foundation |
| [**ScribbleDash**](https://github.com/ankit-verma-209171/scribble-dash) | One codebase on Android and iOS: a sketching game in Compose Multiplatform |
| [**AniFlow**](https://github.com/ankit-verma-209171/AniFlow) | Offline-first architecture: Room cache synced through Paging 3 `RemoteMediator` |
| [**RustInteropDemo**](https://github.com/ankit-verma-209171/RustInteropDemo) | Native performance on Android: Kotlin calling Rust over JNI, raced against the JVM |
| [**Process death, explained**](https://github.com/ankit-verma-209171/android-process-death-recovery-demo) | State that survives: `remember` vs `rememberSaveable` vs `ViewModel` vs `SavedStateHandle` |

### Let's talk

If you're working on something interesting, I'd be glad to hear about it.
[LinkedIn](https://www.linkedin.com/in/ankit-verma-209171/) · [Email](mailto:ankitverma209171@gmail.com) · [LeetCode](https://leetcode.com/u/ankit-verma-209171/)
"""


def build():
    out = {}
    for theme, p in THEMES.items():
        out[ASSETS / f"hero-{theme}.svg"] = hero(p).render()
        out[ASSETS / f"loop-{theme}.svg"] = loop(p).render()
        for slug, name, tag, _, seed, desc in SPOTS:
            out[ASSETS / f"spot-{slug}-{theme}.svg"] = spot(p, name, tag, desc, seed).render()
    spots = "\n".join(picture(f"spot-{slug}", f"{name}: {desc}", "49%", url) for slug, name, _, url, _, desc in SPOTS)
    out[ROOT / "README.md"] = README.replace("@HERO@", picture("hero", HERO_ALT)).replace("@LOOP@", picture("loop", LOOP_ALT)).replace("@SPOTS@", spots)
    return out


def main():
    out = build()
    stale = set(ASSETS.glob("*.svg")) - set(out)
    if "--check" in sys.argv:
        changed = [path for path, text in out.items() if not path.exists() or path.read_text(encoding="utf-8") != text]
        for path in sorted(changed + list(stale)):
            print(f"out of date: {path.relative_to(ROOT)}")
        sys.exit(1 if changed or stale else 0)
    ASSETS.mkdir(exist_ok=True)
    for path in stale:
        path.unlink()
    for path, text in out.items():
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
