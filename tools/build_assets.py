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
INK_NAVY = "#1b1840"     # light-mode text
INK_PURPLE = "#3b2470"   # light-mode headings
INK_GOLD = "#8a5a12"     # light-mode ornaments

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


BADGES = [  # pills used under the project cards
    # slug, label, icon, kind
    ("python", "Python", "python", "brand"),
    ("sql", "SQL", "database", "concept"),
    ("duckdb", "DuckDB", "duckdb", "brand"),
    ("typescript", "TypeScript", "typescript", "brand"),
    ("react", "React", "react", "brand"),
    ("fastapi", "FastAPI", "fastapi", "brand"),
    ("streamlit", "Streamlit", "streamlit", "brand"),
    ("electron", "Electron", "electron", "brand"),
    ("or-tools", "OR-Tools", "optimize", "concept"),
    ("monte-carlo", "Monte Carlo", "montecarlo", "concept"),
]


# ------------------------------------------------------------------ about icons
ABOUT_ICONS = {
    "study": '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5"/><path d="M22 9v5"/>',
    "experience": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M3 13h18"/>',
    "build": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    "direction": '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
}


def about_icon(slug: str) -> None:
    """Small line glyphs that sit inline with the About Me sentences (light + dark)."""
    for theme, col in (("dark", GOLD_LIGHT), ("light", INK_GOLD)):
        body = (f'<g fill="none" stroke="{col}" stroke-width="1.9" stroke-linecap="round" '
                f'stroke-linejoin="round">{ABOUT_ICONS[slug]}</g>')
        write(f"profile/{theme}/about-{slug}.svg", svg(24, 24, body, "", decorative=True))


# ------------------------------------------------------------------ compact headings
def heading(slug: str, title: str) -> None:
    """Centered small-caps title framed by an orbit line and two stars."""
    size, track = 24, 5
    tw = F["label"].width(title, size, track)
    w, h = tw + 2 * 150, 52
    for theme, ink, orn in (("dark", GOLD_LIGHT, GOLD), ("light", INK_PURPLE, INK_GOLD)):
        b = [text("label", title, size, w / 2, 34, ink, "middle", track)]
        for side in (-1, 1):
            x0 = w / 2 + side * (tw / 2 + 18)
            x1 = w / 2 + side * (tw / 2 + 128)
            b.append(f'<path d="M{x0:.1f} 26Q{(x0 + x1) / 2:.1f} {26 + 7:.1f} {x1:.1f} 26" fill="none" '
                     f'stroke="{orn}" stroke-width="1.3" stroke-opacity="0.85"/>')
            b.append(sparkle(x0, 26, 5, orn))
            b.append(f'<circle cx="{x1 + side * 6:.1f}" cy="26" r="2.4" fill="{orn}"/>')
        b.append(sparkle(w / 2 + tw / 2 + 4, 9, 3.2, orn))
        write(f"profile/{theme}/heading-{slug}.svg", svg(math.ceil(w), h, "".join(b), title.title()))


# ------------------------------------------------------------------ tech stack board
STACK = [
    ("Business Analytics & Strategy", [
        ("Excel", "excel", "concept"), ("SQL", "database", "concept"),
        ("Financial Modeling", "finance", "concept"), ("Monte Carlo", "montecarlo", "concept"),
        ("OR-Tools", "optimize", "concept"), ("Forecasting", "forecast", "concept")]),
    ("Applied AI", [
        ("LLM Integration", "llm", "concept"), ("Model Evaluation", "evaluate", "concept"),
        ("scikit-learn", "scikitlearn", "brand"), ("Ollama", "ollama", "brand")]),
    ("Engineering & Data", [
        ("Python", "python", "brand"), ("TypeScript", "typescript", "brand"),
        ("React", "react", "brand"), ("FastAPI", "fastapi", "brand"),
        ("PostgreSQL", "postgresql", "brand"), ("DuckDB", "duckdb", "brand"),
        ("Java / Spring Boot", "springboot", "brand")]),
    ("Development & Delivery", [
        ("Git", "git", "brand"), ("pytest", "pytest", "brand"), ("Jira", "jira", "brand"),
        ("Agile / Scrum", "agile", "concept"), ("Requirements", "requirements", "concept")]),
]

THEMES = {
    "dark": dict(bg0=NAVY, bg1=PURPLE, frame=GOLD, tile=NAVY_2, tile_stroke=GOLD, label=CREAM,
                 cat=GOLD_LIGHT, concept=GOLD_LIGHT, rule=GOLD, star=CREAM),
    "light": dict(bg0="#fbf6ea", bg1="#f1e8f7", frame=INK_GOLD, tile="#ffffff", tile_stroke=INK_GOLD,
                  label=INK_NAVY, cat=INK_PURPLE, concept=INK_GOLD, rule=INK_GOLD, star=INK_GOLD),
}


def darken_for_light(color: str, bg: str = "#ffffff", target: float = 2.6) -> str:
    c, b = hex_to_rgb(color), lum(hex_to_rgb(bg))
    for t in [i / 20 for i in range(21)]:
        m = tuple(v * (1 - t) for v in c)
        if (b + 0.05) / (lum(m) + 0.05) >= target:
            return "#" + "".join(f"{round(v * 255):02x}" for v in m)
    return INK_NAVY


def tile(x: float, y: float, label: str, icon: str, kind: str, theme: str, ts: float = 60,
         fs: float = 11.5) -> str:
    t = THEMES[theme]
    o = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{ts}" height="{ts}" rx="{ts * 0.24:.1f}" fill="{t["tile"]}" '
         f'stroke="{t["tile_stroke"]}" stroke-opacity="0.7" stroke-width="1.2"/>']
    isz = ts * 0.47
    ix, iy, sc = x + (ts - isz) / 2, y + (ts - isz) / 2, isz / 24
    if kind == "brand":
        col = legible(BRAND[icon]) if theme == "dark" else darken_for_light(BRAND[icon])
        o.append(f'<path transform="translate({ix:.1f} {iy:.1f}) scale({sc:.4f})" fill="{col}" d="{simple_icon(icon)}"/>')
    else:
        o.append(f'<g transform="translate({ix:.1f} {iy:.1f}) scale({sc:.4f})" fill="none" stroke="{t["concept"]}" '
                 f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{CONCEPTS[icon]}</g>')
    lines = wrap("sans", label, fs, ts + 24)
    for i, ln in enumerate(lines):
        o.append(text("sans", ln, fs, x + ts / 2, y + ts + fs + 6 + i * (fs + 3), t["label"], "middle"))
    return "".join(o)


def board_shell(w: float, h: float, theme: str, seed: int) -> str:
    t = THEMES[theme]
    uid = f"sb{theme}{int(w)}"
    o = [f'<defs><linearGradient id="{uid}" x1="0" y1="0" x2="1" y2="1">'
         f'<stop offset="0" stop-color="{t["bg0"]}"/><stop offset="1" stop-color="{t["bg1"]}"/></linearGradient></defs>',
         f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="20" fill="url(#{uid})" stroke="{t["frame"]}" stroke-width="1.6"/>',
         f'<rect x="7" y="7" width="{w - 14}" height="{h - 14}" rx="15" fill="none" stroke="{t["frame"]}" stroke-opacity="0.3"/>']
    rnd = random.Random(seed)
    for _ in range(int(w * h / 4200)):
        o.append(f'<circle cx="{rnd.uniform(12, w - 12):.1f}" cy="{rnd.uniform(12, h - 12):.1f}" '
                 f'r="{rnd.choice([0.6, 0.8, 1.1])}" fill="{t["star"]}" fill-opacity="{rnd.uniform(0.2, 0.6):.2f}"/>')
    for cx, cy in [(7, 7), (w - 7, 7), (7, h - 7), (w - 7, h - 7)]:
        o.append(sparkle(cx, cy, 5.5, t["frame"]))
    return "".join(o)


def stack_alt() -> str:
    return "Tech stack — " + "; ".join(f"{c}: " + ", ".join(i[0] for i in items) for c, items in STACK)


def stack_board() -> None:
    alt = stack_alt()
    # desktop: category label column on the left, tiles to the right
    w, left, pitch, ts, row_h, top = 872, 236, 88, 60, 112, 26
    h = top + row_h * len(STACK) + 8
    for theme in THEMES:
        t = THEMES[theme]
        b = [board_shell(w, h, theme, 7)]
        for r, (cat, items) in enumerate(STACK):
            y = top + r * row_h
            parts = cat.upper().split(" & ")
            lines = [parts[0]] + [f"& {x}" for x in parts[1:]]
            cy = y + ts / 2 - (len(lines) - 1) * 9 + 4
            b.append(sparkle(36, cy - 4.5, 4.5, t["cat"]))
            for i, ln in enumerate(lines):
                b.append(text("label", ln, 13, 50, cy + i * 18, t["cat"], tracking=1.4))
            for i, (label, icon, kind) in enumerate(items):
                b.append(tile(left + i * pitch, y + 4, label, icon, kind, theme, ts))
            if r < len(STACK) - 1:
                b.append(f'<line x1="34" y1="{y + row_h - 6}" x2="{w - 34}" y2="{y + row_h - 6}" stroke="{t["rule"]}" '
                         f'stroke-opacity="0.28" stroke-dasharray="2 5"/>')
        write(f"profile/{theme}/stack-board.svg", svg(w, h, "".join(b), alt))
    # mobile: category title on its own line, four tiles per row, larger type
    w, cols, ts, pitch, fs = 400, 4, 64, 92, 13
    x0 = (w - (cols - 1) * pitch - ts) / 2
    layout, y = [], 30
    for cat, items in STACK:
        layout.append(("cat", cat, y))
        y += 22
        for k in range(0, len(items), cols):
            layout.append(("row", items[k:k + cols], y))
            y += ts + 50
        y += 16
    h = y + 6
    for theme in THEMES:
        t = THEMES[theme]
        b = [board_shell(w, h, theme, 8)]
        for kind, payload, yy in layout:
            if kind == "cat":
                b.append(text("label", payload.upper(), 14, w / 2, yy + 8, t["cat"], "middle", 1.6))
            else:
                for i, (label, icon, k) in enumerate(payload):
                    b.append(tile(x0 + i * pitch, yy, label, icon, k, theme, ts, fs))
        write(f"profile/{theme}/stack-board-mobile.svg", svg(w, h, "".join(b), alt))


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



# ------------------------------------------------------------------ project cards (panel style)
CARD_ICONS = {
    "bars": '<path d="M5 20v-5M10 20v-9M15 20v-12M20 20V5"/><path d="M3 21h19"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12.5l9 5 9-5"/><path d="M3 16.5l9 5 9-5"/>',
    "flow": '<rect x="9" y="2.5" width="6" height="5" rx="1"/><rect x="2.5" y="16.5" width="6" height="5" rx="1"/>'
            '<rect x="15.5" y="16.5" width="6" height="5" rx="1"/><path d="M12 7.5v4.5M5.5 16.5V12h13v4.5"/>',
    "shield": '<path d="M12 2.5l8 3v6.2c0 5-3.4 8.4-8 9.8-4.6-1.4-8-4.8-8-9.8V5.5z"/>',
}

CARDS = [
    dict(num="01", title="Technology & AI Investment Strategy", icon="bars", motif=motif_investment, seed=11,
         desc="Prioritizes technology initiatives under budget and resource constraints, plans quarterly "
              "delivery and tracks realized benefits against targets.",
         pills=[("Python", "python", "brand"), ("OR-Tools", "optimize", "concept"), ("SQL", "database", "concept"),
                ("Streamlit", "streamlit", "brand"), ("Monte Carlo", "montecarlo", "concept")]),
    dict(num="02", title="Commercial Analytics & Pricing Strategy", icon="layers", motif=motif_pricing, seed=22,
         desc="Explains revenue changes across 1M+ retail transactions, evaluates customer value and "
              "identifies data-supported pricing opportunities.",
         pills=[("Python", "python", "brand"), ("DuckDB", "duckdb", "brand"), ("FastAPI", "fastapi", "brand"),
                ("React", "react", "brand"), ("TypeScript", "typescript", "brand")]),
    dict(num="03", title="Process-to-Value", icon="flow", motif=motif_process, seed=33,
         desc="In development: analyzing procurement event logs to show where workflows stall, loop back "
              "into rework and need improvement first.",
         pills=[], status="IN DEVELOPMENT", planned="Planned · Python · SQL · PM4Py · BPMN"),
    dict(num="04", title="DoxShield", icon="shield", motif=motif_dome, seed=44,
         desc="Investigates data-sovereignty risks by scanning apps, network connections, cookies and "
              "permissions, keeping the evidence behind every finding.",
         pills=[("Python", "python", "brand"), ("FastAPI", "fastapi", "brand"), ("React", "react", "brand"),
                ("TypeScript", "typescript", "brand"), ("Electron", "electron", "brand")]),
]


def pill(x: float, y: float, label: str, icon: str, kind: str, size: float = 13.5, h: float = 32):
    pad, isz, gap = 11, 16, 7
    tw = F["sans"].width(label, size)
    w = pad + isz + gap + tw + pad
    o = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="{h / 2}" fill="{NAVY}" fill-opacity="0.85" '
         f'stroke="{GOLD}" stroke-opacity="0.8" stroke-width="1.2"/>']
    ix, iy, sc = x + pad, y + (h - isz) / 2, isz / 24
    if kind == "brand":
        o.append(f'<path transform="translate({ix:.1f} {iy:.1f}) scale({sc:.4f})" fill="{legible(BRAND[icon])}" d="{simple_icon(icon)}"/>')
    else:
        o.append(f'<g transform="translate({ix:.1f} {iy:.1f}) scale({sc:.4f})" fill="none" stroke="{GOLD_LIGHT}" '
                 f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{CONCEPTS[icon]}</g>')
    o.append(text("sans", label, size, x + pad + isz + gap, y + h / 2 + size * 0.36, CREAM))
    return "".join(o), w


def leaves(x: float, y: float, s: float, seed: int, flip: bool = False) -> str:
    rnd = random.Random(seed)
    o = []
    for _ in range(9):
        a = rnd.uniform(-70, 70) + (180 if flip else 0)
        dx, dy = rnd.uniform(-26, 26) * s, rnd.uniform(-18, 10) * s
        col = rnd.choice(["#6d4bb0", "#7f5bc4", "#5a3c94", GOLD_DEEP, "#b8873a"])
        o.append(f'<ellipse cx="0" cy="-{9 * s:.1f}" rx="{4.2 * s:.1f}" ry="{9.5 * s:.1f}" fill="{col}" fill-opacity="0.9" '
                 f'transform="translate({x + dx:.1f} {y + dy:.1f}) rotate({a:.0f})"/>')
    return "".join(o)


def card(c: dict, ox: float, oy: float, w: float, mobile: bool, min_h: float = 0) -> tuple[str, float]:
    """One panel in the style of the banner's project panels; returns (svg, height)."""
    uid = f"k{c['num']}{'m' if mobile else 'd'}"
    title_size, desc_size = (38, 25) if mobile else (33, 21.5)
    lx = 112
    motif_w = 178 if mobile else 250
    title_lines = wrap("title", c["title"], title_size, w - lx - (motif_w if mobile else 270))
    title_y = 100
    title_end = title_y + (len(title_lines) - 1) * (title_size + 3)
    desc_w = (w - 64) if mobile else (w - 330)
    desc_top = max(title_end + 46, 190) if mobile else title_end + 44
    desc_lines = wrap("italic", c["desc"], desc_size, desc_w)
    desc_end = desc_top + (len(desc_lines) - 1) * (desc_size + 6)
    pill_rows, row, cur = [], [], 0
    for p in c["pills"]:
        pw = pill(0, 0, *p, size=15 if mobile else 13.5)[1]
        if row and cur + pw > w - 64:
            pill_rows.append(row)
            row, cur = [], 0
        row.append(p)
        cur += pw + 8
    if row:
        pill_rows.append(row)
    rows = max(len(pill_rows), 1)
    pill_h = 34 if mobile else 32
    h = desc_end + 34 + rows * (pill_h + 10) + 26
    if not mobile:
        h = max(h, 340, min_h)
    o = [plaque_defs(uid, w, h)]
    inner = [frame(uid, w, h, 22),
             stars(c["seed"], w, h, 55, avoid=lambda x, y: x < w * 0.62 and 40 < y < h - 70),
             f'<path d="M10 {h - 10}L10 {h - 52}Q{w * 0.2:.0f} {h - 78} {w * 0.42:.0f} {h - 56}T{w - 10} {h - 64}L{w - 10} {h - 10}Z" '
             f'fill="#1c1540" fill-opacity="0.8"/>',
             leaves(28, h - 26, 1.0, c["seed"])]
    if not mobile:
        inner.append(leaves(w - 34, h - 30, 0.9, c["seed"] + 1))
    # header
    inner.append(text("label", f"PROJECT {c['num']}", 15, lx, 50, GOLD, tracking=4.2))
    lw = F["label"].width(f"PROJECT {c['num']}", 15, 4.2)
    inner.append(f'<rect x="{lx + lw + 14:.1f}" y="44.5" width="170" height="1.5" fill="url(#fade{uid})"/>')
    inner.append(f'<rect x="32" y="66" width="58" height="58" rx="11" fill="{NAVY}" fill-opacity="0.7" stroke="url(#gold{uid})" stroke-width="1.8"/>')
    inner.append(f'<g transform="translate(46 80) scale(1.25)" fill="none" stroke="{GOLD_LIGHT}" stroke-width="1.9" '
                 f'stroke-linecap="round" stroke-linejoin="round">{CARD_ICONS[c["icon"]]}</g>')
    for i, ln in enumerate(title_lines):
        inner.append(text("title", ln, title_size, lx, title_y + i * (title_size + 3), CREAM))
    for i, ln in enumerate(desc_lines):
        inner.append(text("italic", ln, desc_size, 36, desc_top + i * (desc_size + 6), CREAM, opacity=0.92))
    # motif
    if mobile:
        inner.append(f'<g transform="translate({w - 162} 44) scale(0.6)">{c["motif"](0, 0)}</g>')
    else:
        inner.append(f'<g transform="translate({w - 268} 52) scale(0.98)">{c["motif"](0, 0)}</g>')
    py = desc_end + 30
    if c.get("status"):
        sw = F["sans_bold"].width(c["status"], 12.5, 2) + 28
        inner.append(f'<rect x="32" y="{py}" width="{sw:.1f}" height="{pill_h}" rx="{pill_h / 2}" fill="{GOLD}" fill-opacity="0.14" '
                     f'stroke="{GOLD}" stroke-width="1.2"/>')
        inner.append(text("sans_bold", c["status"], 12.5, 46, py + pill_h / 2 + 4.5, GOLD_LIGHT, tracking=2))
        inner.append(text("sans", c["planned"], 14 if mobile else 13, 32 + sw + 14, py + pill_h / 2 + 4.8, LAVENDER))
    for r, prow in enumerate(pill_rows):
        x = 32
        for p in prow:
            s, pw = pill(x, py + r * (pill_h + 10), *p, size=15 if mobile else 13.5, h=pill_h)
            inner.append(s)
            x += pw + 8
    o.append(f'<g transform="translate({ox} {oy})">{"".join(inner)}</g>')
    return "".join(o), h


def project_cards() -> None:
    alt = "Featured projects — " + " | ".join(
        f"Project {c['num']}: {c['title']}. {c['desc']}"
        + (f" Tech: {', '.join(p[0] for p in c['pills'])}." if c["pills"] else f" Status: in development. {c['planned']}.")
        for c in CARDS)
    # desktop: 2 x 2 grid
    cw, gap = 760, 28
    parts, heights = [], []
    for c in CARDS:
        heights.append(card(c, 0, 0, cw, False)[1])
    rh = [max(heights[0], heights[1]), max(heights[2], heights[3])]
    for i, c in enumerate(CARDS):
        col, row = i % 2, i // 2
        y = 0 if row == 0 else rh[0] + gap
        s, _ = card(c, col * (cw + gap), y, cw, False, rh[row])
        parts.append(s)
    W, H = 2 * cw + gap, rh[0] + gap + rh[1]
    write("projects/cards.svg", svg(W, H, "".join(parts), alt))
    # mobile: one column
    mw, parts, y = 600, [], 0
    for c in CARDS:
        s, h = card(c, 0, y, mw, True)
        parts.append(s)
        y += h + 24
    write("projects/cards-mobile.svg", svg(mw, y - 24, "".join(parts), alt))


def main() -> None:
    F.update(load_faces())
    for slug, title in (("about", "ABOUT ME"), ("stack", "TECH STACK"),
                        ("projects", "FEATURED PROJECTS")):
        heading(slug, title)
    section_header("connect", "LET\u2019S CONNECT", "Open to conversations about strategy, analytics and applied AI", 4)
    stack_board()
    project_cards()
    for k in ABOUT_ICONS:
        about_icon(k)
    contact_button("github", "GITHUB", "sohamshindework", "github", "brand")
    contact_button("linkedin", "LINKEDIN", "Soham Shinde", "linkedin", "brand")
    contact_button("email", "EMAIL", "sohamshindework@gmail.com", "mail", "concept")
    footer()
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
