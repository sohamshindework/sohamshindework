#!/usr/bin/env python3
"""Generate the SVG artwork for Soham Shinde's GitHub profile README.

Every piece of text is converted to vector outlines (HarfBuzz shaping +
fontTools), so the SVGs render identically for every visitor, need no web
fonts, and contain no scripts or remote references.

Usage:
    python3 -m venv .venv && .venv/bin/pip install fonttools uharfbuzz
    .venv/bin/python tools/build_assets.py

Fonts (all SIL Open Font License) are downloaded once from github.com/google/fonts
into tools/.cache/. Technology logos come from Simple Icons (CC0) in tools/icons/.
The banner (assets/banner.webp) is never touched by this script.
"""
from __future__ import annotations

import math
import random
import re
import urllib.request
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONS = Path(__file__).resolve().parent / "icons"
CACHE = Path(__file__).resolve().parent / ".cache"

# ------------------------------------------------------------------ palette
NAVY = "#0b1030"
NAVY_2 = "#141238"
PURPLE = "#2a1a55"
PURPLE_GLOW = "#5b3a9e"
GOLD = "#e0b25a"
GOLD_LIGHT = "#f5d590"
GOLD_DEEP = "#a8772c"
CREAM = "#f6ead2"
LAVENDER = "#c3b6e6"

# ------------------------------------------------------------------ fonts
FONT_SOURCES = {
    "Cinzel[wght].ttf": "ofl/cinzel/Cinzel%5Bwght%5D.ttf",
    "CormorantGaramond[wght].ttf": "ofl/cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf",
    "CormorantGaramond-Italic[wght].ttf": "ofl/cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf",
    "Inter[opsz,wght].ttf": "ofl/inter/Inter%5Bopsz,wght%5D.ttf",
}
FACES = {  # key: (variable file, axis location)
    "label": ("Cinzel[wght].ttf", {"wght": 600}),
    "title": ("CormorantGaramond[wght].ttf", {"wght": 700}),
    "italic": ("CormorantGaramond-Italic[wght].ttf", {"wght": 600}),
    "sans": ("Inter[opsz,wght].ttf", {"wght": 500, "opsz": 18}),
    "sans_bold": ("Inter[opsz,wght].ttf", {"wght": 600, "opsz": 18}),
}


class Face:
    def __init__(self, path: Path):
        self.tt = TTFont(path)
        self.glyphs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.upem = self.tt["head"].unitsPerEm
        blob = hb.Blob(path.read_bytes())
        self.hb_font = hb.Font(hb.Face(blob))

    def shape(self, text: str):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb_font, buf, {"kern": True, "liga": True})
        return buf.glyph_infos, buf.glyph_positions

    def width(self, text: str, size: float, tracking: float = 0) -> float:
        _, pos = self.shape(text)
        s = size / self.upem
        return sum(p.x_advance for p in pos) * s + tracking * max(len(pos) - 1, 0)

    def path(self, text: str, size: float, x: float, y: float,
             anchor: str = "start", tracking: float = 0) -> str:
        infos, pos = self.shape(text)
        s = size / self.upem
        w = self.width(text, size, tracking)
        if anchor == "middle":
            x -= w / 2
        elif anchor == "end":
            x -= w
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        cx = x
        for info, p in zip(infos, pos):
            name = self.order[info.codepoint]
            t = TransformPen(pen, (s, 0, 0, -s, cx + p.x_offset * s, y - p.y_offset * s))
            self.glyphs[name].draw(t)
            cx += p.x_advance * s + tracking
        return pen.getCommands()


def load_faces() -> dict[str, Face]:
    CACHE.mkdir(exist_ok=True)
    faces = {}
    for key, (src, loc) in FACES.items():
        var = CACHE / src
        if not var.exists():
            url = "https://raw.githubusercontent.com/google/fonts/main/" + FONT_SOURCES[src]
            urllib.request.urlretrieve(url, var)
        tag = "-".join(f"{k}{v}" for k, v in loc.items())
        static = CACHE / f"{var.stem}-{tag}.ttf"
        if not static.exists():
            font = TTFont(var)
            instancer.instantiateVariableFont(font, loc, inplace=True)
            font.save(static)
        faces[key] = Face(static)
    return faces


F: dict[str, Face] = {}


def text(face: str, s: str, size: float, x: float, y: float, fill: str,
         anchor: str = "start", tracking: float = 0, opacity: float | None = None) -> str:
    d = F[face].path(s, size, x, y, anchor, tracking)
    op = f' fill-opacity="{opacity}"' if opacity is not None else ""
    return f'<path fill="{fill}"{op} d="{d}"/>'


def wrap(face: str, s: str, size: float, max_w: float) -> list[str]:
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if F[face].width(trial, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


# ------------------------------------------------------------------ helpers
def svg(w: float, h: float, body: str, label: str, decorative: bool = False) -> str:
    label = label.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    a11y = 'aria-hidden="true"' if decorative else f'role="img" aria-label="{label}"'
    title = "" if decorative else f"<title>{label}</title>"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" '
            f'viewBox="0 0 {w:g} {h:g}" {a11y}>{title}{body}</svg>\n')


def stars(seed: int, w: float, h: float, n: int, avoid=None) -> str:
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        x, y = rnd.uniform(8, w - 8), rnd.uniform(8, h - 8)
        if avoid and avoid(x, y):
            continue
        r = rnd.choice([0.6, 0.8, 0.9, 1.1, 1.4])
        op = rnd.uniform(0.35, 0.9)
        col = rnd.choice([CREAM, CREAM, GOLD_LIGHT, LAVENDER])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{col}" fill-opacity="{op:.2f}"/>')
    return "".join(out)


def sparkle(x: float, y: float, r: float, fill: str = GOLD_LIGHT) -> str:
    k = r * 0.22
    return (f'<path fill="{fill}" d="M{x:g} {y - r:g}Q{x + k:g} {y - k:g} {x + r:g} {y:g}'
            f'Q{x + k:g} {y + k:g} {x:g} {y + r:g}Q{x - k:g} {y + k:g} {x - r:g} {y:g}'
            f'Q{x - k:g} {y - k:g} {x:g} {y - r:g}Z"/>')


def plaque_defs(uid: str, w: float, h: float) -> str:
    return (
        f'<defs>'
        f'<linearGradient id="bg{uid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{NAVY}"/><stop offset="0.55" stop-color="{NAVY_2}"/>'
        f'<stop offset="1" stop-color="{PURPLE}"/></linearGradient>'
        f'<radialGradient id="glow{uid}" cx="0.82" cy="0.35" r="0.6">'
        f'<stop offset="0" stop-color="{PURPLE_GLOW}" stop-opacity="0.55"/>'
        f'<stop offset="1" stop-color="{PURPLE_GLOW}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="gold{uid}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{GOLD_DEEP}"/><stop offset="0.5" stop-color="{GOLD_LIGHT}"/>'
        f'<stop offset="1" stop-color="{GOLD_DEEP}"/></linearGradient>'
        f'<linearGradient id="fade{uid}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0.9"/>'
        f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0"/></linearGradient>'
        f'</defs>'
    )


def frame(uid: str, w: float, h: float, r: float = 18) -> str:
    """Navy plaque with a gold double border and corner ornaments."""
    o = [f'<rect x="1.5" y="1.5" width="{w - 3:g}" height="{h - 3:g}" rx="{r}" fill="url(#bg{uid})"/>',
         f'<rect x="1.5" y="1.5" width="{w - 3:g}" height="{h - 3:g}" rx="{r}" fill="url(#glow{uid})"/>',
         f'<rect x="1.5" y="1.5" width="{w - 3:g}" height="{h - 3:g}" rx="{r}" fill="none" '
         f'stroke="url(#gold{uid})" stroke-width="2.2"/>',
         f'<rect x="8" y="8" width="{w - 16:g}" height="{h - 16:g}" rx="{r - 6}" fill="none" '
         f'stroke="{GOLD}" stroke-opacity="0.35" stroke-width="1"/>']
    for cx, cy in [(8, 8), (w - 8, 8), (8, h - 8), (w - 8, h - 8)]:
        o.append(sparkle(cx, cy, 6))
    o.append(sparkle(w / 2, 1.5, 9))
    return "".join(o)


def write(rel: str, content: str) -> None:
    p = ASSETS / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ------------------------------------------------------------------ section headers
def section_header(slug: str, title: str, subtitle: str, seed: int) -> None:
    w, h = 800, 112
    uid = slug
    body = [plaque_defs(uid, w, h), frame(uid, w, h, 16), stars(seed, w, h, 60,
            avoid=lambda x, y: 180 < x < 620 and 20 < y < 95)]
    tw = F["label"].width(title, 32, 7)
    body.append(text("label", title, 32, w / 2, 56, GOLD_LIGHT, "middle", 7))
    gap = tw / 2 + 26
    for side in (-1, 1):
        x0 = w / 2 + side * gap
        x1 = w / 2 + side * (gap + 120)
        body.append(f'<line x1="{x0:g}" y1="45" x2="{x1:g}" y2="45" stroke="{GOLD}" stroke-opacity="0.75" stroke-width="1.4"/>')
        body.append(sparkle(x0 + side * 4, 45, 5))
        body.append(f'<circle cx="{x1 + side * 6:g}" cy="45" r="2.2" fill="{GOLD}"/>')
    body.append(text("italic", subtitle, 25, w / 2, 89, CREAM, "middle", 0.4, opacity=0.9))
    write(f"sections/{slug}.svg", svg(w, h, "".join(body), f"{title.title()} — {subtitle}"))


# ------------------------------------------------------------------ project motifs
def motif_investment(ox: float, oy: float) -> str:
    """Telescope on a cliff pointing at a rising chart, with a constellation."""
    g = []
    # chart panel
    g.append(f'<g transform="translate({ox + 95} {oy + 18}) skewY(-6)">'
             f'<rect width="128" height="92" rx="6" fill="{PURPLE}" fill-opacity="0.55" stroke="{GOLD}" stroke-opacity="0.8" stroke-width="1.4"/>')
    for i, bh in enumerate([18, 28, 40, 52, 68]):
        g.append(f'<rect x="{14 + i * 22}" y="{82 - bh}" width="13" height="{bh}" rx="2" fill="{GOLD}" fill-opacity="{0.55 + i * 0.09:.2f}"/>')
    g.append(f'<polyline points="18,58 40,48 62,40 84,26 108,12" fill="none" stroke="{CREAM}" stroke-width="1.6"/>')
    g.append(f'<circle cx="108" cy="12" r="3" fill="{GOLD_LIGHT}"/></g>')
    # constellation
    pts = [(ox + 18, oy + 22), (ox + 40, oy + 8), (ox + 62, oy + 30), (ox + 78, oy + 14)]
    g.append(f'<polyline points="{" ".join(f"{x},{y}" for x, y in pts)}" fill="none" stroke="{GOLD_LIGHT}" stroke-opacity="0.6" stroke-width="1"/>')
    g += [f'<circle cx="{x}" cy="{y}" r="2.3" fill="{GOLD_LIGHT}"/>' for x, y in pts]
    # cliff
    g.append(f'<path d="M{ox - 6} {oy + 196}L{ox + 4} {oy + 162}Q{ox + 20} {oy + 150} {ox + 44} {oy + 150}'
             f'L{ox + 96} {oy + 147}Q{ox + 116} {oy + 150} {ox + 126} {oy + 166}L{ox + 136} {oy + 196}Z" fill="#3a2c66"/>')
    g.append(f'<path d="M{ox + 4} {oy + 162}Q{ox + 20} {oy + 150} {ox + 44} {oy + 150}L{ox + 96} {oy + 147}'
             f'Q{ox + 116} {oy + 150} {ox + 126} {oy + 166}" fill="none" stroke="{GOLD}" stroke-opacity="0.55" stroke-width="1.4"/>')
    # tripod
    tx, ty = ox + 60, oy + 110
    for dx in (-24, 0, 24):
        g.append(f'<line x1="{tx}" y1="{ty}" x2="{tx + dx}" y2="{ty + 38}" stroke="{GOLD_DEEP}" stroke-width="3" stroke-linecap="round"/>')
    # telescope tube
    g.append(f'<g transform="translate({tx} {ty}) rotate(-28)">'
             f'<rect x="-34" y="-9" width="86" height="18" rx="4" fill="{GOLD}"/>'
             f'<rect x="48" y="-12" width="14" height="24" rx="3" fill="{GOLD_LIGHT}"/>'
             f'<rect x="-46" y="-6" width="14" height="12" rx="2" fill="{GOLD_DEEP}"/>'
             f'<rect x="-10" y="-9" width="4" height="18" fill="{GOLD_DEEP}"/></g>')
    g.append(f'<circle cx="{tx}" cy="{ty}" r="4" fill="{GOLD_DEEP}"/>')
    return "".join(g)


def motif_pricing(ox: float, oy: float) -> str:
    g = []
    # coin stacks
    for sx, n in [(ox + 20, 4), (ox + 64, 6), (ox + 150, 3)]:
        for i in range(n):
            y = oy + 168 - i * 11
            g.append(f'<ellipse cx="{sx + 20}" cy="{y + 6}" rx="22" ry="7" fill="{GOLD_DEEP}"/>')
            g.append(f'<ellipse cx="{sx + 20}" cy="{y}" rx="22" ry="7" fill="{GOLD}" stroke="{GOLD_LIGHT}" stroke-width="1"/>')
    # tag
    g.append(f'<g transform="translate({ox + 118} {oy + 72}) rotate(-18)">'
             f'<path d="M-30 -42L30 -42L46 -16L46 52Q46 58 40 58L-40 58Q-46 58 -46 52L-46 -16Z" '
             f'fill="#e9c98a" stroke="{GOLD_DEEP}" stroke-width="2"/>'
             f'<circle cx="0" cy="-22" r="7" fill="{NAVY_2}" stroke="{GOLD_DEEP}" stroke-width="2"/>'
             f'<circle cx="-12" cy="8" r="7" fill="none" stroke="{NAVY}" stroke-width="5"/>'
             f'<circle cx="14" cy="38" r="7" fill="none" stroke="{NAVY}" stroke-width="5"/>'
             f'<line x1="16" y1="2" x2="-14" y2="44" stroke="{NAVY}" stroke-width="5" stroke-linecap="round"/></g>')
    # string
    g.append(f'<path d="M{ox + 112} {oy + 51}Q{ox + 140} {oy + 2} {ox + 172} {oy + 30}" fill="none" stroke="{GOLD_LIGHT}" stroke-width="2"/>')
    # shooting star
    g.append(f'<line x1="{ox + 10}" y1="{oy + 40}" x2="{ox + 60}" y2="{oy + 12}" stroke="{GOLD_LIGHT}" stroke-opacity="0.5" stroke-width="1.5" stroke-linecap="round"/>')
    g.append(sparkle(ox + 62, oy + 11, 5))
    return "".join(g)


def motif_process(ox: float, oy: float) -> str:
    g = []
    mx, my, mw, mh = ox + 6, oy + 18, 186, 122
    g.append(f'<rect x="{mx}" y="{my}" width="{mw}" height="{mh}" rx="10" fill="#2b2148" stroke="{GOLD}" stroke-width="2.5"/>')
    g.append(f'<rect x="{mx + 10}" y="{my + 10}" width="{mw - 20}" height="{mh - 20}" rx="4" fill="#161236"/>')
    # stand
    g.append(f'<path d="M{mx + mw / 2 - 16} {my + mh}L{mx + mw / 2 + 16} {my + mh}L{mx + mw / 2 + 26} {my + mh + 26}L{mx + mw / 2 - 26} {my + mh + 26}Z" fill="{GOLD_DEEP}"/>')
    g.append(f'<rect x="{mx + mw / 2 - 48}" y="{my + mh + 24}" width="96" height="7" rx="3" fill="{GOLD}"/>')
    # flow nodes
    nodes = [(26, 32), (74, 22), (74, 54), (122, 38)]
    nodes = [(mx + x, my + y) for x, y in nodes]
    edges = [(0, 1), (0, 2), (1, 3), (2, 3)]
    for a, b in edges:
        (x1, y1), (x2, y2) = nodes[a], nodes[b]
        g.append(f'<path d="M{x1 + 18} {y1 + 6}C{x1 + 30} {y1 + 6} {x2 - 12} {y2 + 6} {x2} {y2 + 6}" fill="none" stroke="{LAVENDER}" stroke-width="1.4"/>')
    for i, (x, y) in enumerate(nodes):
        col = "#e7a3a3" if i == 2 else GOLD
        g.append(f'<rect x="{x}" y="{y}" width="20" height="12" rx="3" fill="{col}"/>')
    # rework loop on the bottleneck node
    x, y = nodes[2]
    g.append(f'<path d="M{x + 4} {y + 13}q6 12 12 0" fill="none" stroke="#e7a3a3" stroke-width="1.4"/>')
    # mini bars
    for i, bh in enumerate([10, 16, 12, 22, 28]):
        g.append(f'<rect x="{mx + 130 + i * 9}" y="{my + 100 - bh}" width="6" height="{bh}" fill="{GOLD_LIGHT}" fill-opacity="0.85"/>')
    return "".join(g)


def motif_dome(ox: float, oy: float) -> str:
    g = []
    cx, cy, r = ox + 100, oy + 158, 92
    g.append(f'<defs><radialGradient id="domeglow" cx="0.5" cy="0.75" r="0.6">'
             f'<stop offset="0" stop-color="{GOLD_LIGHT}" stop-opacity="0.55"/>'
             f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0.04"/></radialGradient></defs>')
    g.append(f'<path d="M{cx - r} {cy}A{r} {r} 0 0 1 {cx + r} {cy}Z" fill="url(#domeglow)" stroke="{GOLD}" stroke-width="2.4"/>')
    # geodesic lattice: latitude arcs and meridians
    for frac in (0.33, 0.62, 0.86):
        yy = cy - r * frac
        half = math.sqrt(r * r - (r * frac) ** 2)
        g.append(f'<line x1="{cx - half:.1f}" y1="{yy:.1f}" x2="{cx + half:.1f}" y2="{yy:.1f}" stroke="{GOLD}" stroke-opacity="0.75" stroke-width="1.2"/>')
    for ang in (-60, -30, 0, 30, 60):
        ex = cx + r * math.sin(math.radians(ang))
        g.append(f'<path d="M{cx} {cy - r}Q{cx + (ex - cx) * 1.05:.1f} {cy - r * 0.45:.1f} {ex:.1f} {cy}" fill="none" stroke="{GOLD}" stroke-opacity="0.7" stroke-width="1.2"/>')
    # base
    g.append(f'<rect x="{cx - r - 12}" y="{cy}" width="{2 * r + 24}" height="12" rx="5" fill="{GOLD_DEEP}"/>')
    g.append(f'<rect x="{cx - r - 24}" y="{cy + 12}" width="{2 * r + 48}" height="10" rx="4" fill="#3a2c5c"/>')
    # padlock
    lx, ly = cx - 18, cy - 54
    g.append(f'<path d="M{lx + 7} {ly}V{ly - 10}a11 11 0 0 1 22 0V{ly}" fill="none" stroke="{GOLD_LIGHT}" stroke-width="5"/>')
    g.append(f'<rect x="{lx}" y="{ly}" width="36" height="30" rx="5" fill="{GOLD}" stroke="{GOLD_LIGHT}" stroke-width="1.5"/>')
    g.append(f'<circle cx="{lx + 18}" cy="{ly + 12}" r="4" fill="{NAVY}"/>')
    g.append(f'<rect x="{lx + 16}" y="{ly + 13}" width="4" height="10" rx="1.5" fill="{NAVY}"/>')
    return "".join(g)


PROJECTS = [
    ("01", "Technology & AI Investment Strategy", motif_investment, 11, None),
    ("02", "Commercial Analytics & Pricing Strategy", motif_pricing, 22, None),
    ("03", "Process-to-Value", motif_process, 33, "IN DEVELOPMENT"),
    ("04", "DoxShield", motif_dome, 44, None),
]


def project_plaque(num: str, title: str, motif, seed: int, status: str | None) -> None:
    w, h = 800, 236
    uid = f"p{num}"
    body = [plaque_defs(uid, w, h), frame(uid, w, h, 18),
            stars(seed, w, h, 70, avoid=lambda x, y: x < 520 and 30 < y < 200)]
    # hills silhouette along the bottom
    body.append(f'<path d="M10 {h - 10}L10 {h - 40}Q120 {h - 62} 230 {h - 44}T470 {h - 40}T{w - 10} {h - 46}L{w - 10} {h - 10}Z" fill="#1d1640" fill-opacity="0.85"/>')
    lx = 46
    body.append(text("label", f"PROJECT {num}", 17, lx, 58, GOLD, tracking=4.5))
    lw = F["label"].width(f"PROJECT {num}", 17, 4.5)
    body.append(f'<rect x="{lx + lw + 16:.1f}" y="51" width="150" height="1.6" fill="url(#fade{uid})"/>')
    lines = wrap("title", title, 50, 470)
    y0 = 118 if len(lines) == 1 else 106
    for i, ln in enumerate(lines):
        body.append(text("title", ln, 50, lx, y0 + i * 52, CREAM))
    if status:
        sw = F["sans_bold"].width(status, 13, 2) + 28
        sy = y0 + (len(lines) - 1) * 52 + 26
        body.append(f'<rect x="{lx}" y="{sy}" width="{sw:.1f}" height="28" rx="14" fill="{GOLD}" fill-opacity="0.12" stroke="{GOLD}" stroke-width="1.2"/>')
        body.append(text("sans_bold", status, 13, lx + 14, sy + 19, GOLD_LIGHT, tracking=2))
    body.append(motif(w - 250, 20))
    label = f"Project {num}: {title}" + (f" ({status.lower()})" if status else "")
    write(f"projects/project-{num}.svg", svg(w, h, "".join(body), label))


# ------------------------------------------------------------------ badges
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lum(c):
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def legible(color: str, bg: str = NAVY_2, target: float = 4.0) -> str:
    """Lighten a brand colour toward white until it reads on the navy badge."""
    c, b = hex_to_rgb(color), lum(hex_to_rgb(bg))
    for t in [i / 20 for i in range(21)]:
        m = tuple(v + (1 - v) * t for v in c)
        if (lum(m) + 0.05) / (b + 0.05) >= target:
            return "#" + "".join(f"{round(v * 255):02x}" for v in m)
    return "#ffffff"


def simple_icon(name: str) -> str:
    raw = (ICONS / f"{name}.svg").read_text()
    return re.search(r' d="([^"]+)"', raw).group(1)


BRAND = {  # Simple Icons slug -> brand hex
    "python": "#3776AB", "postgresql": "#4169E1", "duckdb": "#FFF000", "react": "#61DAFB",
    "typescript": "#3178C6", "fastapi": "#009688", "springboot": "#6DB33F", "openjdk": "#F89820",
    "git": "#F05032", "pytest": "#0A9EDC", "jira": "#0052CC", "streamlit": "#FF4B4B",
    "electron": "#9FEAF9", "ollama": "#FFFFFF", "scikitlearn": "#F7931E", "pandas": "#E70488",
    "github": "#FFFFFF", "linkedin": "#0A66C2", "gmail": "#EA4335",
}

# Original line glyphs (24x24, stroke) for concepts that have no product logo.
CONCEPTS = {
    "excel": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14.5h18M9 4v16M15 4v16"/>',
    "finance": '<path d="M4 20V10M10 20V6M16 20v-8M3 20h18"/><path d="M4 7l6-3 6 5 5-4"/>',
    "montecarlo": '<path d="M3 19c3 0 4-12 9-12s6 12 9 12"/><circle cx="7" cy="9" r="1"/><circle cx="12" cy="4" r="1"/><circle cx="17" cy="10" r="1"/><circle cx="15" cy="15" r="1"/><circle cx="9" cy="15" r="1"/>',
    "optimize": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
    "forecast": '<path d="M3 20h18"/><path d="M3 16l4-4 4 2 3-4"/><path d="M14 10l3-3 4-2" stroke-dasharray="2 2"/>',
    "llm": '<path d="M4 5h16v10H9l-5 4z"/><circle cx="9" cy="10" r="1"/><circle cx="12" cy="10" r="1"/><circle cx="15" cy="10" r="1"/>',
    "evaluate": '<path d="M4 6h10M4 12h10M4 18h10"/><path d="M16 6l2 2 3-4M16 12l2 2 3-4M16 18l2 2 3-4"/>',
    "agile": '<path d="M20 12a8 8 0 1 1-3-6.2"/><path d="M17 2v4h4"/><path d="M9 12l2 2 4-4"/>',
    "requirements": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 3v3h6V3M8 11h8M8 15h6"/>',
    "database": '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
}


def badge(slug: str, label: str, icon: str, kind: str = "brand") -> None:
    size = 15
    pad, gap, isz = 14, 9, 18
    tw = F["sans"].width(label, size, 0.2)
    w = pad + isz + gap + tw + pad
    h = 36
    body = [f'<rect x="0.75" y="0.75" width="{w - 1.5:.1f}" height="{h - 1.5}" rx="{(h - 1.5) / 2}" '
            f'fill="{NAVY_2}" stroke="{GOLD}" stroke-opacity="0.85" stroke-width="1.3"/>']
    s = isz / 24
    if kind == "brand":
        col = legible(BRAND[icon])
        body.append(f'<path transform="translate({pad} {(h - isz) / 2}) scale({s:.4f})" fill="{col}" d="{simple_icon(icon)}"/>')
    else:
        body.append(f'<g transform="translate({pad} {(h - isz) / 2}) scale({s:.4f})" fill="none" stroke="{GOLD_LIGHT}" '
                    f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{CONCEPTS[icon]}</g>')
    body.append(text("sans", label, size, pad + isz + gap, h / 2 + 5.4, CREAM, tracking=0.2))
    write(f"badges/{slug}.svg", svg(math.ceil(w), h, "".join(body), label))


BADGES = [
    # slug, label, icon, kind
    ("python", "Python", "python", "brand"),
    ("sql", "SQL", "database", "concept"),
    ("postgresql", "PostgreSQL", "postgresql", "brand"),
    ("duckdb", "DuckDB", "duckdb", "brand"),
    ("typescript", "TypeScript", "typescript", "brand"),
    ("react", "React", "react", "brand"),
    ("fastapi", "FastAPI", "fastapi", "brand"),
    ("spring-boot", "Java / Spring Boot", "springboot", "brand"),
    ("streamlit", "Streamlit", "streamlit", "brand"),
    ("electron", "Electron", "electron", "brand"),
    ("scikit-learn", "scikit-learn", "scikitlearn", "brand"),
    ("pandas", "pandas", "pandas", "brand"),
    ("ollama", "Ollama", "ollama", "brand"),
    ("git", "Git", "git", "brand"),
    ("pytest", "pytest", "pytest", "brand"),
    ("jira", "Jira", "jira", "brand"),
    ("or-tools", "OR-Tools", "optimize", "concept"),
    ("excel", "Excel", "excel", "concept"),
    ("financial-modeling", "Financial Modeling", "finance", "concept"),
    ("monte-carlo", "Monte Carlo", "montecarlo", "concept"),
    ("forecasting", "Forecasting", "forecast", "concept"),
    ("llm-integration", "LLM Integration", "llm", "concept"),
    ("model-evaluation", "Model Evaluation", "evaluate", "concept"),
    ("agile-scrum", "Agile / Scrum", "agile", "concept"),
    ("requirements", "Requirements Analysis", "requirements", "concept"),
]


# ------------------------------------------------------------------ about icons
ABOUT_ICONS = {
    "study": '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5"/><path d="M22 9v5"/>',
    "experience": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M3 13h18"/>',
    "build": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    "direction": '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
}


def about_icon(slug: str) -> None:
    s = 48
    body = (f'<circle cx="24" cy="24" r="22.5" fill="{NAVY_2}" stroke="{GOLD}" stroke-width="1.5"/>'
            f'<g transform="translate(12 12)" fill="none" stroke="{GOLD_LIGHT}" stroke-width="1.7" '
            f'stroke-linecap="round" stroke-linejoin="round">{ABOUT_ICONS[slug]}</g>')
    write(f"icons/{slug}.svg", svg(s, s, body, "", decorative=True))


# ------------------------------------------------------------------ contact buttons
def contact_button(slug: str, label: str, sub: str, icon: str, kind: str, w: float = 274) -> None:
    h = 64
    uid = f"c{slug}"
    body = [plaque_defs(uid, w, h),
            f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="32" fill="url(#bg{uid})" stroke="url(#gold{uid})" stroke-width="2"/>',
            f'<circle cx="32" cy="32" r="20" fill="{NAVY}" stroke="{GOLD}" stroke-opacity="0.7"/>']
    if kind == "brand":
        body.append(f'<path transform="translate(21 21) scale({22 / 24:.4f})" fill="{legible(BRAND[icon], NAVY, 6)}" d="{simple_icon(icon)}"/>')
    else:
        body.append(f'<g transform="translate(21 21) scale({22 / 24:.4f})" fill="none" stroke="{GOLD_LIGHT}" stroke-width="1.8" '
                    f'stroke-linecap="round" stroke-linejoin="round">{CONCEPTS[icon]}</g>')
    body.append(text("label", label, 19, 64, 31, GOLD_LIGHT, tracking=2.5))
    body.append(text("sans", sub, 12.5, 64, 49, CREAM, opacity=0.85))
    write(f"contact/{slug}.svg", svg(w, h, "".join(body), f"{label}: {sub}"))


def footer() -> None:
    w, h = 800, 40
    body = [f'<defs><linearGradient id="fl" x1="0" x2="1"><stop offset="0" stop-color="{GOLD}" stop-opacity="0"/>'
            f'<stop offset="0.5" stop-color="{GOLD}"/><stop offset="1" stop-color="{GOLD}" stop-opacity="0"/></linearGradient></defs>',
            f'<rect x="60" y="19.3" width="{w - 120}" height="1.4" fill="url(#fl)"/>',
            sparkle(w / 2, 20, 11), sparkle(w / 2 - 34, 20, 5), sparkle(w / 2 + 34, 20, 5)]
    write("sections/divider.svg", svg(w, h, "".join(body), "", decorative=True))


def main() -> None:
    F.update(load_faces())
    section_header("about", "ABOUT ME", "Where engineering judgment meets business questions", 1)
    section_header("stack", "TECH STACK", "Tools I have used in shipped work and projects", 2)
    section_header("projects", "FEATURED PROJECTS", "Four questions, four working systems", 3)
    section_header("connect", "LET’S CONNECT", "Open to conversations about strategy, analytics and applied AI", 4)
    for p in PROJECTS:
        project_plaque(*p)
    for b in BADGES:
        badge(*b)
    for k in ABOUT_ICONS:
        about_icon(k)
    contact_button("github", "GITHUB", "sohamshindework", "github", "brand")
    contact_button("linkedin", "LINKEDIN", "Soham Shinde", "linkedin", "brand")
    contact_button("email", "EMAIL", "sohamshindework@gmail.com", "mail", "concept")
    footer()
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
