#!/usr/bin/env python3
"""Builds README.md and assets/*.svg (light and dark variants).

Needs fonttools and brotli:  pip install fonttools brotli
Run from anywhere:            python3 scripts/build_profile.py
"""

import base64
import io
import math
from html import escape
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONT_DIR = Path(__file__).resolve().parent / "fonts"
FALLBACK = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
W = 840

LIGHT = dict(
    surface="#F6EBE4", surface2="#EDDDD4", ink="#231A16", muted="#6E5D55",
    primary="#A23F16", on_primary="#FFFFFF", pc="#FFDBCF", on_pc="#3A0B00",
    sc="#E2DFFF", on_sc="#1B1653", sec="#5A55A8",
    tc="#BFF0DA", on_tc="#00382A", ter="#1C6B55",
    yc="#FFE08A", on_yc="#3A2E00", yel="#8A6B00",
)
DARK = dict(
    surface="#231C18", surface2="#30261F", ink="#F0DFD8", muted="#B9A79F",
    primary="#FFB59B", on_primary="#5C1900", pc="#7F2B06", on_pc="#FFDBCF",
    sc="#3B3779", on_sc="#E2DFFF", sec="#C3C0FF",
    tc="#0E5140", on_tc="#BFF0DA", ter="#8FD5BD",
    yc="#574500", on_yc="#FFE08A", yel="#E9C349",
)
THEMES = {"light": LIGHT, "dark": DARK}
# (container, on-container, accent) triples used to give each card its own tone.
TONES = [("pc", "on_pc", "primary"), ("sc", "on_sc", "sec"), ("tc", "on_tc", "ter"), ("yc", "on_yc", "yel")]


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
            tt = TTFont(self.path)
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
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.parts, self.defs, self.css = [], [], []
        self.used = {k: set() for k in FONTS}
        self._ids = 0

    def uid(self, prefix):
        self._ids += 1
        return f"{prefix}{self._ids}"

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


def cookie(k, depth):
    return lambda t: 1 + depth * math.cos(k * t)


def squircle(p=4.0):
    return lambda t: (abs(math.cos(t)) ** p + abs(math.sin(t)) ** p) ** (-1 / p) * 0.92


def clover(k=4):
    return lambda t: 0.78 + 0.22 * abs(math.cos(k * t / 2)) ** 0.6


SHAPES = {
    "cookie9": cookie(9, 0.07),
    "cookie12": cookie(12, 0.05),
    "cookie4": cookie(4, 0.12),
    "flower": cookie(6, 0.16),
    "squircle": squircle(),
    "clover": clover(4),
    "circle": lambda t: 0.95,
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


def tile(svg, x, y, w, h, fill, r=28):
    cid = svg.uid("clip")
    svg.defs.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/></clipPath>')
    svg.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"/>')
    return cid


def clipped(svg, cid, draw):
    svg.add(f'<g clip-path="url(#{cid})">')
    draw()
    svg.add("</g>")


def chip(svg, x, y, label, fill, ink, size=12, pad=12, h=26):
    w = FONTS["bold"].width(label, size, 0.4) + pad * 2
    svg.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="{h / 2}" fill="{fill}"/>')
    svg.text(x + pad, y + h / 2 + size * 0.36, label, "bold", size, ink, spacing=0.4)
    return w


# ---- Hero

HERO_ALT = (
    "Ankit Verma, mobile software engineer. Ships to Android and iOS. Currently learning Compose Multiplatform. "
    "Favourite kind of bug: the crash that only shows up after you open the same screen again, and again, and again. "
    "Based in India. Beyond mobile: AR and geospatial, on-device ML, tools for AI agents."
)


def hero(p):
    g = 12
    top_h, side_h = 280, 134
    row2_y, row2_h = top_h + g, 200
    svg = Svg(W, row2_y + row2_h, HERO_ALT)

    # Name
    a = tile(svg, 0, 0, 516, top_h, p["pc"])
    clipped(svg, a, lambda: shape(svg, 452, 236, 128, "cookie9", p["primary"], 0.2, morph=["flower", "squircle"], spin=60))
    clipped(svg, a, lambda: shape(svg, 470, 52, 20, "cookie4", p["primary"], 0.55, spin=-18))
    svg.text(32, 50, "Hi, I'm", "bold", 17, p["on_pc"], opacity=0.75)
    svg.text(28, 132, "Ankit", "display", 92, p["on_pc"], spacing=-1.5, max_w=420)
    svg.text(28, 214, "Verma", "display", 92, p["on_pc"], spacing=-1.5, max_w=420)
    svg.text(32, 252, "Mobile software engineer", "bold", 19, p["on_pc"], opacity=0.85)

    # Platforms
    bx = 528
    b = tile(svg, bx, 0, 312, side_h, p["sc"])
    svg.text(bx + 24, 38, "Ships to", "bold", 15, p["on_sc"], opacity=0.75)
    svg.text(bx + 24, 84, "Android & iOS", "display", 32, p["on_sc"], spacing=-0.5, max_w=230)
    svg.text(bx + 24, 112, "Kotlin · Compose · Swift · SwiftUI", "text", 14, p["on_sc"], opacity=0.8, max_w=264)
    for i, px in enumerate((bx + 254, bx + 280)):
        svg.add(f'<rect x="{px}" y="16" width="22" height="40" rx="6" fill="none" stroke="{p["on_sc"]}" stroke-width="2"/>')
        notch = (f'<circle cx="{px + 11}" cy="21" r="1.6" fill="{p["on_sc"]}"/>' if i == 0
                 else f'<rect x="{px + 7}" y="19.5" width="8" height="3" rx="1.5" fill="{p["on_sc"]}"/>')
        svg.add(notch)

    # Now learning
    c = tile(svg, bx, side_h + g, 312, side_h, p["tc"])
    clipped(svg, c, lambda: shape(svg, bx + 290, side_h + g + 118, 46, "flower", p["ter"], 0.35, spin=30))
    cy = side_h + g
    svg.text(bx + 24, cy + 38, "Currently learning", "bold", 15, p["on_tc"], opacity=0.75)
    svg.text(bx + 24, cy + 78, "Compose", "display", 30, p["on_tc"], spacing=-0.5, max_w=230)
    svg.text(bx + 24, cy + 110, "Multiplatform", "display", 30, p["on_tc"], spacing=-0.5, max_w=230)

    # Favourite bug
    d = tile(svg, 0, row2_y, 300, row2_h, p["yc"])
    svg.text(24, row2_y + 38, "Favourite kind of bug", "bold", 15, p["on_yc"], opacity=0.75)
    quote = "The crash that only shows up after you open the same screen again, and again, and again."
    for i, line in enumerate(wrap(quote, "bold", 19, 250)):
        svg.text(24, row2_y + 74 + i * 25, line, "bold", 19, p["on_yc"], max_w=252)
    svg.text(24, row2_y + row2_h - 22, "(it was a reference cycle)", "text", 14, p["on_yc"], opacity=0.7)
    clipped(svg, d, lambda: shape(svg, 286, row2_y + row2_h - 8, 34, "clover", p["yel"], 0.3, spin=-24))

    # Location
    ex = 312
    tile(svg, ex, row2_y, 240, row2_h, p["surface"])
    svg.text(ex + 24, row2_y + 38, "Based in", "bold", 15, p["muted"])
    shape(svg, ex + 186, row2_y + 62, 34, "cookie12", p["yel"], spin=40)
    svg.text(ex + 22, row2_y + 156, "India", "display", 52, p["ink"], spacing=-1, max_w=196)
    svg.text(ex + 24, row2_y + 180, "IST · UTC+5:30", "text", 14, p["muted"])

    # Beyond mobile
    fx = 564
    f = tile(svg, fx, row2_y, 276, row2_h, p["primary"])
    clipped(svg, f, lambda: shape(svg, fx + 262, row2_y + 16, 40, "squircle", p["on_primary"], 0.12, spin=50))
    svg.text(fx + 24, row2_y + 38, "Beyond mobile", "bold", 15, p["on_primary"], opacity=0.8)
    for i, line in enumerate(["AR & geospatial", "On-device ML", "Tools for AI agents"]):
        svg.text(fx + 24, row2_y + 80 + i * 32, line, "display", 23, p["on_primary"], spacing=-0.3, max_w=228)
    return svg


# ---- Section headings

SECTIONS = {
    "bugs": ("Bug journal", "production problems I've tracked down", "cookie9", "primary"),
    "built": ("Things I've built", "shipped, open-sourced, or just for fun", "flower", "sec"),
    "toolbox": ("Toolbox", "what I reach for", "squircle", "ter"),
    "hello": ("Say hi", "always happy to talk shop", "clover", "yel"),
}


def heading(p, key):
    title, caption, shp, accent = SECTIONS[key]
    svg = Svg(W, 64, title)
    shape(svg, 20, 34, 18, shp, p[accent], spin=36)
    svg.text(52, 45, title, "display", 32, p["ink"], spacing=-0.5)
    svg.text(W, 44, caption, "text", 15, p["muted"], anchor="end")
    return svg


# ---- Bug journal

BUGS = [
    ("iOS · UIKit · Instruments",
     "App ran out of memory after repeated trips through media-heavy forms",
     "Strong reference cycles in table view cells kept every visited screen alive, and image loading held on to more than it needed.",
     "Broke the cycles and corrected how images were loaded and released."),
    ("Android · CameraX · TensorFlow Lite",
     "Real-time camera scanning lost stability as the ML pipeline ran",
     "Object lifecycles in the frame pipeline were too long, and each frame did intermediate work it didn't need.",
     "Tightened lifecycles and removed the unnecessary computations."),
    ("iOS · audio & video",
     "Recorded media arrived corrupted, worst on flaky networks",
     "Recording configuration and encoding didn't match, and uploads weren't handled safely under poor connectivity.",
     "Corrected the recording setup, encoding and upload handling."),
    ("iOS · server-driven UI",
     "Editing one nested form quietly overwrote data in another",
     "State updates weren't scoped, so a change in one subform leaked into other instances.",
     "Isolated updates to the active subform."),
]


def bug_card_layout(platform, title, cause, fix, w):
    inner = w - 48
    t_lines = wrap(title, "display", 21, inner)
    c_lines = wrap(cause, "text", 15, inner)
    f_lines = wrap(fix, "text", 15, inner)
    h = 24 + 26 + 22 + len(t_lines) * 26 + 18 + 18 + len(c_lines) * 21 + 14 + 18 + len(f_lines) * 21 + 20
    return t_lines, c_lines, f_lines, h


def bug_journal(p):
    cw, gap = (W - 12) / 2, 12
    layouts = [bug_card_layout(*b, cw) for b in BUGS]
    rows = [max(layouts[i][3], layouts[i + 1][3]) for i in range(0, len(BUGS), 2)]
    total_h = sum(rows) + gap * (len(rows) - 1)
    alt = "Bug journal. " + " ".join(f"{t}. Cause: {c} Fix: {f}" for _, t, c, f in BUGS)
    svg = Svg(W, total_h, alt)
    shapes = ["cookie4", "flower", "clover", "squircle"]
    y = 0
    for r, row_h in enumerate(rows):
        for col in range(2):
            i = r * 2 + col
            platform = BUGS[i][0]
            t_lines, c_lines, f_lines, _ = layouts[i]
            fill, ink, accent = TONES[i % len(TONES)]
            x = col * (cw + gap)
            cid = tile(svg, x, y, cw, row_h, p["surface"], r=24)
            clipped(svg, cid, lambda: shape(svg, x + cw - 14, y + 14, 30, shapes[i], p[accent], 0.9, spin=45 if i % 2 else -45))
            chip(svg, x + 24, y + 24, platform, p[fill], p[ink])
            ty = y + 24 + 26 + 30
            for j, line in enumerate(t_lines):
                svg.text(x + 24, ty + j * 26, line, "display", 21, p["ink"], spacing=-0.2)
            cy = ty + (len(t_lines) - 1) * 26 + 34
            svg.text(x + 24, cy, "CAUSE", "bold", 11, p[accent], spacing=1.6)
            for j, line in enumerate(c_lines):
                svg.text(x + 24, cy + 20 + j * 21, line, "text", 15, p["ink"], opacity=0.88)
            fy = cy + 20 + (len(c_lines) - 1) * 21 + 32
            svg.text(x + 24, fy, "FIX", "bold", 11, p[accent], spacing=1.6)
            for j, line in enumerate(f_lines):
                svg.text(x + 24, fy + 20 + j * 21, line, "text", 15, p["ink"], opacity=0.88)
        y += row_h + gap
    return svg


# ---- Project cards (one image each, so each can link to its repo)

PROJECTS = [
    ("miraro", "Miraro", "Shipped · Play Store", "https://miraro.zettamask.com",
     "A privacy-first gallery: hide and share the photos you choose, without handing over the whole device."),
    ("android-docs-mcp", "android-docs-mcp", "AI agents · TypeScript", "https://github.com/ankit-verma-209171/android-docs-mcp",
     "An MCP server that lets AI coding agents search developer.android.com docs, API references and release notes."),
    ("ar-treasure-hunt", "AR Treasure Hunt", "AR R&D · Unity · ARCore", "https://github.com/SimformSolutionsPvtLtd/SS-ARTreasureHunt",
     "Geospatial AR: 3D clues anchored to real-world coordinates with ARCore and AR Foundation. Open-sourced prototype."),
    ("aniflow", "AniFlow", "Android · Compose", "https://github.com/ankit-verma-209171/AniFlow",
     "Offline-first anime browser. Room cache, synced through Paging 3 RemoteMediator when the network is back."),
    ("rust-interop", "RustInteropDemo", "Kotlin + Rust · JNI", "https://github.com/ankit-verma-209171/RustInteropDemo",
     "Kotlin calls native Rust over JNI, with a live race to count to a billion: JVM vs Rust."),
    ("process-death", "Process death, explained", "Android · state", "https://github.com/ankit-verma-209171/android-process-death-recovery-demo",
     "remember, rememberSaveable, ViewModel and SavedStateHandle, put through rotation and process death."),
]
CARD_W = 414


def project_cards(p):
    inner = CARD_W - 48
    descs = [wrap(d, "text", 15, inner) for *_, d in PROJECTS]
    h = 24 + 28 + 26 + 34 + max(len(d) for d in descs) * 21 + 26
    out = {}
    shapes = ["cookie9", "flower", "clover", "squircle", "cookie4", "cookie12"]
    for i, ((slug, name, tag, _, desc), lines) in enumerate(zip(PROJECTS, descs)):
        fill, ink, accent = TONES[i % len(TONES)]
        svg = Svg(CARD_W, h, f"{name}. {tag}. {desc}")
        cid = tile(svg, 0, 0, CARD_W, h, p[fill])
        clipped(svg, cid, lambda: shape(svg, CARD_W - 30, h - 20, 64, shapes[i], p[accent], 0.22, spin=60 if i % 2 else -60))
        chip(svg, 24, 24, tag, p[ink], p[fill])
        svg.add(f'<circle cx="{CARD_W - 40}" cy="40" r="17" fill="{p[ink]}"/>')
        svg.add(
            f'<path d="M{CARD_W - 45} 45 L{CARD_W - 35} 35 M{CARD_W - 42} 35 H{CARD_W - 35} V42" '
            f'stroke="{p[fill]}" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        svg.text(24, 24 + 28 + 40, name, "display", 27, p[ink], spacing=-0.4, max_w=inner)
        for j, line in enumerate(lines):
            svg.text(24, 24 + 28 + 40 + 30 + j * 21, line, "text", 15, p[ink], opacity=0.85)
        out[slug] = svg
    return out


# ---- Toolbox

TOOLBOX = [
    ("Build", ["Kotlin", "Jetpack Compose", "Compose Multiplatform", "Coroutines & Flow", "Hilt", "Room", "Swift", "SwiftUI", "UIKit"]),
    ("See & sense", ["CameraX", "TensorFlow Lite", "ARKit", "RealityKit", "RoomPlan", "ARCore Geospatial", "AR Foundation"]),
    ("Debug & ship", ["Instruments", "Memory profiling", "WorkManager", "Firebase", "CI/CD", "Play Store", "App Store"]),
    ("Tinker", ["TypeScript", "Python", "Rust", "Go", "C", "MCP servers"]),
]


def toolbox(p):
    cw, gap = (W - 12) / 2, 12
    layouts = []
    for title, items in TOOLBOX:
        rows, cur, x = [], [], 0
        for item in items:
            w = FONTS["bold"].width(item, 13, 0.3) + 28
            if cur and x + w > cw - 48:
                rows.append(cur)
                cur, x = [], 0
            cur.append(item)
            x += w + 8
        rows.append(cur)
        layouts.append(rows)
    heights = [24 + 30 + 18 + len(r) * 38 + 14 for r in layouts]
    row_hs = [max(heights[0], heights[1]), max(heights[2], heights[3])]
    alt = "Toolbox. " + " ".join(f"{t}: {', '.join(items)}." for t, items in TOOLBOX)
    svg = Svg(W, sum(row_hs) + gap, alt)
    y = 0
    for r, row_h in enumerate(row_hs):
        for col in range(2):
            i = r * 2 + col
            fill, ink, accent = TONES[i]
            x = col * (cw + gap)
            tile(svg, x, y, cw, row_h, p["surface"], r=24)
            shape(svg, x + 36, y + 42, 12, ["cookie9", "flower", "squircle", "clover"][i], p[accent])
            svg.text(x + 56, y + 50, TOOLBOX[i][0], "display", 23, p["ink"], spacing=-0.3)
            cy = y + 24 + 30 + 18
            for row in layouts[i]:
                cx = x + 24
                for item in row:
                    cx += chip(svg, cx, cy, item, p[fill], p[ink], size=13, pad=14, h=30) + 8
                cy += 38
        y += row_h + gap
    return svg


# ---- Contact pills and footer

CONTACTS = [
    ("linkedin", "LinkedIn", "https://www.linkedin.com/in/ankit-verma-209171/", 0),
    ("leetcode", "LeetCode", "https://leetcode.com/u/ankit-verma-209171/", 2),
    ("email", "Email me", "mailto:ankitverma209171@gmail.com", 1),
]


def contact_pill(p, label, tone):
    fill, ink, accent = TONES[tone]
    tw = FONTS["bold"].width(label, 17)
    w, h = tw + 96, 56
    svg = Svg(w, h, label)
    svg.add(f'<rect width="{w:.1f}" height="{h}" rx="{h / 2}" fill="{p[fill]}"/>')
    shape(svg, 30, 28, 11, "cookie9", p[accent], spin=20)
    svg.text(50, 34, label, "bold", 17, p[ink])
    ax = 50 + tw + 14
    svg.add(
        f'<path d="M{ax:.1f} 34 L{ax + 10:.1f} 24 M{ax + 3:.1f} 24 H{ax + 10:.1f} V31" stroke="{p[ink]}" '
        f'stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    return svg


def footer(p):
    svg = Svg(W, 110, "Thanks for stopping by.")
    names = ["cookie9", "flower", "squircle", "clover", "cookie4"]
    accents = ["primary", "sec", "ter", "yel", "primary"]
    for i, (n, a) in enumerate(zip(names, accents)):
        nxt = [names[(i + 1) % 5], names[(i + 2) % 5]]
        shape(svg, W / 2 - 96 + i * 48, 32, 15, n, p[a], morph=nxt)
    svg.text(W / 2, 92, "Thanks for stopping by.", "bold", 17, p["muted"], anchor="middle")
    return svg


# ---- README

INTRO = (
    "I build mobile apps that don't just work, but keep working well as they grow. Most days that means Kotlin and "
    "Jetpack Compose; other days it's Swift in a production iOS codebase, an AR prototype, or a tool that helps AI "
    "agents read the Android docs. I like owning features end to end, and I like the bugs most people would rather not touch."
)


def picture(name, alt, width=None, href=None):
    w = f' width="{width}"' if width else ""
    img = (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
        f'<img src="assets/{name}-light.svg" alt="{escape(alt)}"{w}></picture>'
    )
    return f'<a href="{href}">{img}</a>' if href else img


def readme():
    h = lambda k: picture(f"heading-{k}", SECTIONS[k][0], "100%")
    cards = [picture(f"project-{slug}", f"{name}: {desc}", "49%", url) for slug, name, _, url, desc in PROJECTS]
    projects = "\n</p>\n<p>\n".join("\n".join(cards[i:i + 2]) for i in range(0, len(cards), 2))
    contacts = "\n".join(picture(f"contact-{slug}", label, None, url) for slug, label, url, _ in CONTACTS)
    return f"""<!-- Generated by scripts/build_profile.py. Edit the script, then run it. -->

{picture("hero", HERO_ALT, "100%")}

{INTRO}

{h("bugs")}

{picture("bugs", "Bug journal: " + " ".join(f"{t}." for _, t, _, _ in BUGS), "100%")}

{h("built")}

<p>
{projects}
</p>

{h("toolbox")}

{picture("toolbox", "Toolbox: " + "; ".join(f"{t}: {', '.join(i)}" for t, i in TOOLBOX), "100%")}

{h("hello")}

<p>
{contacts}
</p>

{picture("footer", "Thanks for stopping by.", "100%")}
"""


def main():
    ASSETS.mkdir(exist_ok=True)
    for old in ASSETS.glob("*.svg"):
        old.unlink()
    for theme, p in THEMES.items():
        files = {"hero": hero(p), "bugs": bug_journal(p), "toolbox": toolbox(p), "footer": footer(p)}
        files.update({f"heading-{k}": heading(p, k) for k in SECTIONS})
        files.update({f"project-{k}": v for k, v in project_cards(p).items()})
        files.update({f"contact-{slug}": contact_pill(p, label, tone) for slug, label, _, tone in CONTACTS})
        for name, svg in files.items():
            (ASSETS / f"{name}-{theme}.svg").write_text(svg.render(), encoding="utf-8")
    (ROOT / "README.md").write_text(readme(), encoding="utf-8")


if __name__ == "__main__":
    main()
