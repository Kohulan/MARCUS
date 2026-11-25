"""Draws the README's graphics as SVG, in the web UI's "survey sheet" look, light and dark.

    uvx --with fonttools --with brotli --with rdkit python docs/assets/readme/build.py

Writes hero-{light,dark}.svg, pipeline-{light,dark}.svg and architecture-{light,dark}.svg
next to this file. Colours are the UI's tokens (frontend-v2/src/styles/tokens.css); the
fonts are the UI's own (Geist, Geist Mono), subset to the letters each drawing uses and
embedded, since an SVG shown as an image may load nothing from outside. The motion plays
once, from the image's first paint, ends on the drawing at rest, and stops under reduced
motion. The structure is quercetin, drawn by RDKit.
"""

from __future__ import annotations

import base64
import html
import io
import re
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

HERE = Path(__file__).resolve().parent
FONTS = HERE.parents[2] / "frontend-v2" / "node_modules" / "@fontsource"
FONT_FILES = {
    "g400": FONTS / "geist/files/geist-latin-400-normal.woff2",
    "g700": FONTS / "geist/files/geist-latin-700-normal.woff2",
    "m400": FONTS / "geist-mono/files/geist-mono-latin-400-normal.woff2",
    "m500": FONTS / "geist-mono/files/geist-mono-latin-500-normal.woff2",
}
FAMILY = {"g400": ("G", 400), "g700": ("G", 700), "m400": ("M", 400), "m500": ("M", 500)}

THEMES = {
    "light": {
        "paper": "#F4F3EA", "surface": "#FFFFFF", "sunken": "#ECEBE1", "ink": "#1C211D",
        "text2": "#3F443D", "muted": "#5E625B", "line": "#B9BCB2", "hair": "#D9DACF",
        "green": "#1E4D33", "accepted": "#2D7A46", "orange": "#FA3600", "oink": "#B82800",
        "onorange": "#141414", "atomO": "#C42B00",
    },
    "dark": {
        "paper": "#161A17", "surface": "#1D221E", "sunken": "#202621", "ink": "#ECEBE1",
        "text2": "#CFD0C6", "muted": "#A2A69C", "line": "#465046", "hair": "#2E352F",
        "green": "#8FD3A6", "accepted": "#74CC90", "orange": "#FF5B2B", "oink": "#FF8A63",
        "onorange": "#141414", "atomO": "#FF7A52",
    },
}

EASE = "cubic-bezier(0.22, 1, 0.36, 1)"

# --- fonts --------------------------------------------------------------------------------

_used: dict[str, set[str]] = {k: set() for k in FONT_FILES}
_metrics: dict[str, TTFont] = {}


def font(key: str) -> TTFont:
    if key not in _metrics:
        _metrics[key] = TTFont(FONT_FILES[key])
    return _metrics[key]


def width(text: str, key: str, size: float, tracking: float = 0.0) -> float:
    """Advance width of `text` in px (no kerning), with letter spacing in em."""
    f = font(key)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    adv = sum(hmtx[cmap[ord(c)]][0] for c in text if ord(c) in cmap)
    return adv / upm * size + tracking * size * len(text)


def t(x, y, text, key, size, fill, cls="", anchor="start", tracking=0.0, extra=""):
    """One line of text in one of the four faces; records its letters for the subset."""
    _used[key].update(text)
    fam, weight = FAMILY[key]
    ls = f' letter-spacing="{tracking}em"' if tracking else ""
    c = f' class="{cls}"' if cls else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam}" font-weight="{weight}" '
        f'font-size="{size}" fill="{fill}" text-anchor="{anchor}"{ls}{c}{extra}>'
        f"{html.escape(text)}</text>"
    )


def font_faces() -> str:
    rules = []
    for key, path in FONT_FILES.items():
        chars = _used[key]
        if not chars:
            continue
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["kern", "liga"]
        opts.name_IDs = []
        opts.notdef_outline = True
        f = TTFont(path)
        sub = subset.Subsetter(opts)
        sub.populate(text="".join(sorted(chars)) + " ")
        sub.subset(f)
        buf = io.BytesIO()
        f.flavor = "woff2"
        f.save(buf)
        data = base64.b64encode(buf.getvalue()).decode()
        fam, weight = FAMILY[key]
        rules.append(
            f"@font-face{{font-family:{fam};font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{data}) format('woff2')}}"
        )
    return "".join(rules)


def reset_fonts() -> None:
    for s in _used.values():
        s.clear()


# --- shared pieces ------------------------------------------------------------------------

BASE_CSS = f"""
.draw{{stroke-dasharray:1;animation:draw var(--d,800ms) {EASE} var(--t,0ms) backwards}}
.fade{{animation:fade var(--d,600ms) {EASE} var(--t,0ms) backwards}}
.rise{{animation:rise var(--d,600ms) {EASE} var(--t,0ms) backwards}}
.fall{{transform-box:fill-box;animation:fall var(--d,760ms) cubic-bezier(.5,0,.75,0) var(--t,0ms) backwards,land 260ms {EASE} calc(var(--t,0ms) + var(--d,760ms)) backwards;transform-origin:50% 90%}}
.slide{{animation:slide 560ms {EASE} var(--t,0ms) backwards}}
.grow{{transform-box:fill-box;transform-origin:left;animation:grow var(--d,600ms) {EASE} var(--t,0ms) backwards}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop 520ms {EASE} var(--t,0ms) backwards}}
.stamp{{transform-box:fill-box;transform-origin:center;animation:stamp 420ms cubic-bezier(.3,1.4,.5,1) var(--t,0ms) backwards}}
@keyframes draw{{from{{stroke-dashoffset:1}}}}
@keyframes fade{{from{{opacity:0}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(10px)}}}}
@keyframes fall{{from{{opacity:0;transform:translateY(-70px)}}8%{{opacity:1}}}}
@keyframes land{{from{{transform:scale(1.08,.86)}}}}
@keyframes slide{{from{{opacity:0;transform:translateX(-12px)}}}}
@keyframes grow{{from{{transform:scaleX(0)}}}}
@keyframes pop{{from{{opacity:0;transform:rotate(-90deg) scale(.3)}}}}
@keyframes stamp{{from{{opacity:0;transform:scale(1.8) rotate(8deg)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""


def svg(w: int, h: int, title: str, desc: str, body: str, css: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">'
        f'<title id="t">{html.escape(title)}</title><desc id="d">{html.escape(desc)}</desc>'
        f"<style>{font_faces()}{BASE_CSS}{css}</style>{body}</svg>\n"
    )


def timing(t_ms: int, d_ms: int | None = None) -> str:
    d = f";--d:{d_ms}ms" if d_ms is not None else ""
    return f' style="--t:{t_ms}ms{d}"'


def line(x1, y1, x2, y2, stroke, w=1.0, cls="draw", t_ms=0, d_ms=800, extra=""):
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{w}" '
        f'pathLength="1" class="{cls}"{timing(t_ms, d_ms)}{extra}/>'
    )


def cross(x, y, c, t_ms):
    return (
        f'<g class="pop"{timing(t_ms)}><path d="M{x - 6} {y}h12M{x} {y - 6}v12" '
        f'stroke="{c}" stroke-width="1.2"/></g>'
    )


def frame(w, h, c, order):
    """The sheet's frame as four lines, each drawn from its own end, in the given order."""
    m = 16
    sides = {
        "top": (w - m, m, m, m),
        "right": (w - m, h - m, w - m, m),
        "bottom": (m, h - m, w - m, h - m),
        "left": (m, m, m, h - m),
    }
    out = []
    for i, (name, d_ms) in enumerate(order):
        x1, y1, x2, y2 = sides[name]
        out.append(line(x1, y1, x2, y2, c, 1.2, t_ms=80 + i * 140, d_ms=d_ms))
    return "".join(out)


def ticks(x1, x2, y, c, step=32, t_ms=300):
    path = "".join(
        f"M{x} {y}v{6 if (x - x1) % (step * 4) == 0 else 3}" for x in range(x1, x2 + 1, step)
    )
    return f'<path d="{path}" stroke="{c}" stroke-width="1" class="fade"{timing(t_ms, 900)}/>'


# --- the structure (RDKit) ----------------------------------------------------------------

QUERCETIN = "O=c1c(O)c(-c2ccc(O)c(O)c2)oc2cc(O)cc(O)c12"


def structure(c: dict, size=(230, 190), t0=1400) -> tuple[str, str]:
    """Quercetin's depiction (bonds drawn one by one, labels fading in) and its SMILES."""
    mol = Chem.MolFromSmiles(QUERCETIN)
    rdDepictor.SetPreferCoordGen(True)
    rdDepictor.Compute2DCoords(mol)
    d = rdMolDraw2D.MolDraw2DSVG(*size)
    o = d.drawOptions()
    o.clearBackground = False
    o.bondLineWidth = 2
    o.scaleBondWidth = False
    o.fixedFontSize = 15
    o.padding = 0.06
    o.useBWAtomPalette()
    d.DrawMolecule(mol)
    d.FinishDrawing()
    raw = d.GetDrawingText()
    paths = re.findall(r"<path class='([^']*)' d='([^']*)'[^>]*/>", raw)
    out, bond_i = [], 0
    for cls, dd in paths:
        dd = " ".join(dd.split())
        if cls.startswith("bond-"):
            out.append(
                f'<path d="{dd}" fill="none" stroke="{c["ink"]}" stroke-width="2" '
                f'stroke-linecap="round" pathLength="1" class="draw"'
                f'{timing(t0 + bond_i * 45, 420)}/>'
            )
            bond_i += 1
        elif cls.startswith("atom-"):
            out.append(f'<path d="{dd}" fill="{c["atomO"]}" class="fade"{timing(t0 + 900, 500)}/>')
    return "".join(out), Chem.MolToSmiles(mol)


# --- hero ---------------------------------------------------------------------------------

ACRO = [
    ("M", "olecular", None),
    ("A", "nnotation", "and"),
    ("R", "ecognition", "for"),
    ("C", "urating", None),
    ("U", "nravelled", None),
    ("S", "tructures", None),
]


def wrap(s: str, n: int) -> list[str]:
    """Lines of at most n characters, each broken after a closing bracket where it can be."""
    lines = []
    while len(s) > n:
        cut = s.rfind(")", 0, n) + 1 or n
        lines.append(s[:cut])
        s = s[cut:]
    return [*lines, s]


def hero(theme: str) -> str:
    c = THEMES[theme]
    reset_fonts()
    W, H = 1280, 640
    split, block = 700, 528
    b = [f'<rect width="{W}" height="{H}" fill="{c["paper"]}"/>']
    b.append(frame(W, H, c["line"], [("top", 760), ("left", 640), ("bottom", 820), ("right", 600)]))
    b.append(ticks(48, W - 48, 16, c["line"]))
    b.append(line(split, block, split, 16, c["line"], 1.2, t_ms=0, d_ms=760))
    b.append(line(16, block, W - 16, block, c["line"], 1.2, t_ms=360, d_ms=700))

    # the name, its initials falling into place one by one
    size, lh, x0, y0 = 56, 62, 60, 118
    track = -0.035
    for i, (ini, rest, link) in enumerate(ACRO):
        y = y0 + i * lh
        t_land = 500 + i * 110
        b.append(t(x0, y, ini, "g700", size, c["green"], "fall", tracking=track,
                   extra=timing(t_land, 640)))
        rx = x0 + width(ini, "g700", size, track)
        b.append(t(rx, y, rest, "g400", size, c["ink"], "slide", tracking=track,
                   extra=timing(t_land + 680)))
        if link:
            lx = rx + width(rest, "g400", size, track) + width(" ", "g400", size)
            b.append(t(lx, y, link, "g400", size, c["muted"], "slide", tracking=track,
                       extra=timing(t_land + 760)))
    b.append(t(x0, 486, "From a journal PDF to checked chemical structures for COCONUT.",
               "g400", 20, c["text2"], "rise", extra=timing(1500)))

    # the page: text, the structure drawing in its segmentation box, more text
    px, py, pw, ph = 742, 52, 252, 440
    b.append(f'<g class="rise"{timing(420, 700)}>'
             f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="{c["surface"]}" '
             f'stroke="{c["hair"]}"/></g>')
    b.append(t(px + pw / 2, py - 12, "PAGE 1 OF 5 · 300 DPI", "m400", 10, c["muted"], "fade",
               anchor="middle", tracking=0.08, extra=timing(600)))
    for i, wbar in enumerate([0.86, 0.94, 0.9, 0.62]):
        b.append(f'<rect x="{px + 18}" y="{py + 24 + i * 12}" width="{(pw - 36) * wbar:.0f}" '
                 f'height="5" rx="1" fill="{c["hair"]}" class="grow"{timing(700 + i * 70)}/>')
    bx, by, bw, bh = px + 12, py + 92, pw - 24, 214
    drawing, smiles = structure(c, (int(bw - 8), int(bh - 12)))
    b.append(f'<g transform="translate({bx + 4} {by + 6})">{drawing}</g>')
    b.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="none" '
             f'stroke="{c["orange"]}" stroke-width="2" pathLength="1" class="draw"'
             f'{timing(1150, 700)}/>')
    b.append(f'<g class="fade"{timing(1650, 300)}><rect x="{bx}" y="{by - 18}" width="40" '
             f'height="18" fill="{c["orange"]}"/>'
             + t(bx + 20, by - 5, "[01]", "m500", 11, c["onorange"], anchor="middle")
             + "</g>")
    b.append(t(px + pw / 2, by + bh + 22, "Compound 1", "g400", 12, c["muted"], "fade",
               anchor="middle", extra=timing(1700)))
    for i, wbar in enumerate([0.9, 0.96, 0.74, 0.88, 0.5]):
        b.append(f'<rect x="{px + 18}" y="{by + bh + 44 + i * 12}" '
                 f'width="{(pw - 36) * wbar:.0f}" height="5" rx="1" fill="{c["hair"]}" '
                 f'class="grow"{timing(820 + i * 70)}/>')

    # the arrow, then what MARCUS read
    ax1, ax2, ay = bx + bw + 6, 1034, by + bh / 2
    b.append(line(ax1, ay, ax2 - 4, ay, c["orange"], 2, t_ms=2300, d_ms=380))
    b.append(f'<path d="M{ax2 - 10} {ay - 6}L{ax2} {ay}L{ax2 - 10} {ay + 6}" fill="none" '
             f'stroke="{c["orange"]}" stroke-width="2" stroke-linejoin="round" class="fade"'
             f'{timing(2600, 200)}/>')
    rx = 1048
    b.append(t(rx, by + 16, "SMILES", "m400", 11, c["muted"], "fade", tracking=0.08,
               extra=timing(2550)))
    for i, part in enumerate(wrap(smiles, 22)):
        b.append(t(rx, by + 42 + i * 21, part, "m400", 14, c["ink"], "slide",
                   extra=timing(2650 + i * 140)))
    n = len(wrap(smiles, 22))
    b.append(t(rx, by + 52 + n * 21, "DECIMER · VALID", "m400", 11, c["muted"], "fade",
               tracking=0.08, extra=timing(2650 + n * 140)))
    sx, sy = 1150, by + bh - 6
    b.append(f'<g class="stamp"{timing(3050)}>'
             f'<circle cx="{sx}" cy="{sy}" r="40" fill="none" stroke="{c["accepted"]}" '
             f'stroke-width="2"/><circle cx="{sx}" cy="{sy}" r="34" fill="none" '
             f'stroke="{c["accepted"]}" stroke-width="1"/>'
             + t(sx, sy + 4, "ACCEPTED", "m500", 11, c["accepted"], anchor="middle",
                 tracking=0.06, extra=f' transform="rotate(-14 {sx} {sy})"')
             + "</g>")

    # the title block
    cells = [
        (16, "INPUT", "A journal PDF or one image"),
        (336, "ENGINES", "DECIMER · MolParser · MolScribe"),
        (656, "OUTPUT", "SMILES · molfile · SDF · COCONUT"),
        (976, "LICENCE", "Open source, MIT"),
    ]
    for i, (cx, label, value) in enumerate(cells):
        if cx > 16:
            b.append(line(cx, block, cx, H - 16, c["line"], 1.2, t_ms=500 + i * 90, d_ms=420))
        b.append(t(cx + 24, block + 34, label, "m400", 11, c["muted"], "fade", tracking=0.08,
                   extra=timing(900 + i * 80)))
        b.append(t(cx + 24, block + 64, value, "g400", 17, c["ink"], "rise",
                   extra=timing(950 + i * 80)))
    for i, (x, y) in enumerate([(split, block), (336, block), (656, block), (976, block)]):
        b.append(cross(x, y, c["ink"], 700 + i * 90))
    for i, (x, y) in enumerate([(40, 40), (W - 40, 40), (W - 40, block - 24), (40, block - 24)]):
        b.append(cross(x, y, c["muted"], 600 + [2, 0, 3, 1][i] * 80))

    return svg(
        W, H,
        "MARCUS: Molecular Annotation and Recognition for Curating Unravelled Structures",
        "A drawing sheet: the name spelled out, and a page whose structure drawing, boxed in "
        "orange, becomes a SMILES string and is accepted.",
        "".join(b),
    )


# --- pipeline -----------------------------------------------------------------------------

def icon(kind: str, c: dict, t0: int) -> str:
    s = f'fill="none" stroke="{c["ink"]}" stroke-width="2" stroke-linecap="round" ' \
        f'stroke-linejoin="round" pathLength="1" class="draw"'
    d = lambda i, dur=520: timing(t0 + i * 90, dur)  # noqa: E731
    page = "M-22 -30h30l14 14v46h-44z"
    fold = "M8 -30v14h14"
    if kind == "pdf":
        return (f'<path d="{page}" {s}{d(0)}/><path d="{fold}" {s}{d(1)}/>'
                f'<path d="M-14 -4h28M-14 6h28M-14 16h18" {s}{d(2)}/>')
    if kind == "segment":
        return (f'<path d="{page}" {s}{d(0)}/><path d="{fold}" {s}{d(1)}/>'
                f'<path d="M-15 -8h30v28h-30z" fill="none" stroke="{c["orange"]}" '
                f'stroke-width="2" pathLength="1" class="draw"{d(2)}/>'
                f'<path d="M0 -2l7 4v8l-7 4l-7-4v-8z" {s}{d(3)}/>')
    if kind == "read":
        return (f'<path d="M-18 -18l12 7v14l-12 7l-12-7v-14z" {s}{d(0)}/>'
                f'<path d="M-24 -6v10M-12 -10l8 4" {s}{d(1)}/>'
                f'<path d="M2 -4h10M8 -9l5 5l-5 5" fill="none" stroke="{c["orange"]}" '
                f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
                f'pathLength="1" class="draw"{d(2)}/>'
                f'<path d="M18 -14h14M18 -4h10M18 6h14" {s}{d(3)}/>')
    if kind == "curate":
        return (f'<circle r="24" fill="none" stroke="{c["accepted"]}" stroke-width="2" '
                f'pathLength="1" class="draw"{d(0, 700)}/>'
                f'<circle r="19" fill="none" stroke="{c["accepted"]}" stroke-width="1" '
                f'pathLength="1" class="draw"{d(1, 700)}/>'
                f'<path d="M-9 0l6 6l12-13" fill="none" stroke="{c["accepted"]}" '
                f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" '
                f'pathLength="1" class="draw"{d(3)}/>')
    # coconut: the database the accepted structures go to
    return (f'<ellipse cy="-18" rx="22" ry="7" {s}{d(0)}/>'
            f'<path d="M-22 -18v32c0 4 10 7 22 7s22-3 22-7v-32" {s}{d(1)}/>'
            f'<path d="M-22 -2c0 4 10 7 22 7s22-3 22-7" {s}{d(2)}/>'
            f'<path d="M30 10v-26M24 -10l6-6l6 6" fill="none" stroke="{c["orange"]}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'pathLength="1" class="draw"{d(3)}/>')


def pipeline(theme: str) -> str:
    c = THEMES[theme]
    reset_fonts()
    W, H = 1280, 300
    steps = [
        ("pdf", "PDF", ["A journal article,", "up to 20 MB"]),
        ("segment", "Segment", ["DECIMER Segmentation finds", "every structure drawing"]),
        ("read", "Recognise", ["Four engines turn each", "drawing into SMILES"]),
        ("curate", "Curate", ["You accept, fix or reject,", "one by one or in bulk"]),
        ("coconut", "Submit", ["Accepted structures", "go to COCONUT"]),
    ]
    b = [f'<rect width="{W}" height="{H}" fill="{c["paper"]}"/>']
    b.append(frame(W, H, c["line"], [("left", 400), ("top", 760), ("right", 400), ("bottom", 760)]))
    cw = (W - 32) / len(steps)
    for i, (kind, title, cap) in enumerate(steps):
        x = 16 + i * cw
        cx = x + cw / 2
        t0 = 300 + i * 420
        if i:
            b.append(line(x, 16, x, H - 16, c["hair"], 1, t_ms=200 + i * 80, d_ms=500))
            b.append(f'<g class="pop"{timing(t0 - 120)}>'
                     f'<circle cx="{x}" cy="104" r="11" fill="{c["paper"]}" '
                     f'stroke="{c["line"]}"/><path d="M{x - 3} {99}l5 5l-5 5" fill="none" '
                     f'stroke="{c["orange"]}" stroke-width="2" stroke-linecap="round" '
                     f'stroke-linejoin="round"/></g>')
        b.append(f'<g transform="translate({cx:.1f} 104)">{icon(kind, c, t0)}</g>')
        b.append(t(cx, 184, title, "g700", 22, c["ink"], "rise", anchor="middle",
                   tracking=-0.02, extra=timing(t0 + 200)))
        for j, part in enumerate(cap):
            b.append(t(cx, 214 + j * 18, part, "m400", 12, c["muted"], "fade", anchor="middle",
                       tracking=0.02, extra=timing(t0 + 300)))
    return svg(W, H, "How MARCUS works",
               "PDF, then segmentation, recognition by four engines, curation by a person, "
               "and submission to COCONUT.", "".join(b))


# --- architecture -------------------------------------------------------------------------

def box(x, y, w, h, c, title, sub, t0, accent=None, title_key="g700"):
    out = [f'<g class="rise"{timing(t0, 600)}>'
           f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{c["surface"]}" '
           f'stroke="{accent or c["line"]}" stroke-width="{1.5 if accent else 1}"/>']
    out.append(t(x + 16, y + 28, title, title_key, 17, c["ink"], tracking=-0.01))
    for i, s in enumerate(sub):
        out.append(t(x + 16, y + 50 + i * 17, s, "m400", 11, c["muted"], tracking=0.03))
    out.append("</g>")
    return "".join(out)


def chip(x, y, c, label, t0):
    w = width(label, "m500", 10, 0.08) + 14
    return (f'<g class="fade"{timing(t0)}><rect x="{x}" y="{y}" width="{w:.0f}" height="16" '
            f'fill="{c["green"]}"/>'
            + t(x + 7, y + 11.5, label, "m500", 10, c["paper"], tracking=0.08) + "</g>")


def architecture(theme: str) -> str:
    c = THEMES[theme]
    reset_fonts()
    W, H = 1280, 520
    b = [f'<rect width="{W}" height="{H}" fill="{c["paper"]}"/>']
    b.append(frame(W, H, c["line"], [("top", 760), ("right", 500), ("bottom", 760), ("left", 500)]))
    b.append(ticks(48, W - 48, 16, c["line"], t_ms=200))

    mid = 196
    b.append(box(48, mid - 44, 184, 88, c, "Browser", ["React 18, TypeScript", "no login, no account"], 200))
    b.append(box(272, mid - 60, 212, 120, c, "nginx", ["the only open port", "web UI · /api/v2", "COCONUT relay (TLS)"], 380, accent=c["orange"]))
    b.append(box(524, mid - 60, 224, 120, c, "FastAPI", ["the API, OpenAPI schema", "live updates (SSE)", "dispatcher · metrics"], 560))
    b.append(box(524, mid + 100, 106, 72, c, "Postgres", ["papers"], 740))
    b.append(box(642, mid + 100, 106, 72, c, "Redis", ["queues"], 820))
    for x1, x2 in [(232, 272), (484, 524)]:
        b.append(line(x1, mid, x2, mid, c["ink"], 1.5, t_ms=600, d_ms=400))
    b.append(line(577, mid + 60, 577, mid + 100, c["ink"], 1.5, t_ms=900, d_ms=300))
    b.append(line(695, mid + 60, 695, mid + 100, c["ink"], 1.5, t_ms=960, d_ms=300))

    queues = [
        ("q.cpu", "PDF check, pages, Docling text", False),
        ("q.tools", "CDK depictions, similarity", False),
        ("q.segment", "DECIMER Segmentation", True),
        ("q.decimer", "DECIMER, DECIMER hand-drawn", True),
        ("q.molparser", "MolParser", True),
        ("q.molscribe", "MolScribe", True),
        ("q.llm", "the MARCUS model (llama.cpp)", True),
    ]
    qx, qy, qh = 812, 56, 58
    bus = 780
    b.append(line(748, mid, bus, mid, c["ink"], 1.5, t_ms=1000, d_ms=300))
    b.append(line(bus, qy + qh / 2 - 6, bus, qy + (len(queues) - 1) * qh + qh / 2 - 6, c["ink"], 1.5,
                  t_ms=1200, d_ms=600))
    b.append(t(qx, qy - 16, "CELERY WORKERS · ONE QUEUE PER KIND OF WORK", "m400", 10,
               c["muted"], "fade", tracking=0.08, extra=timing(1100)))
    for i, (q, what, gpu) in enumerate(queues):
        y = qy + i * qh
        t0 = 1300 + i * 110
        b.append(line(bus, y + qh / 2 - 6, qx, y + qh / 2 - 6, c["ink"], 1.5, t_ms=t0, d_ms=240))
        b.append(f'<g class="slide"{timing(t0 + 100)}>'
                 f'<rect x="{qx}" y="{y}" width="{W - 48 - qx}" height="{qh - 12}" '
                 f'fill="{c["surface"]}" stroke="{c["line"]}"/>'
                 + t(qx + 16, y + 28, q, "m500", 14, c["ink"])
                 + t(qx + 190, y + 28, what, "g400", 15, c["text2"])
                 + "</g>")
        if gpu:
            b.append(chip(qx + 130, y + 15, c, "GPU", t0 + 300))
    b.append(t(48, H - 40, "Docker Compose · nginx is the only published port · no paper text "
               "leaves the server", "m400", 11, c["muted"], "fade", tracking=0.06,
               extra=timing(2200)))
    return svg(W, H, "MARCUS architecture",
               "The browser talks to nginx, which serves the web UI and passes /api/v2 to "
               "FastAPI on Postgres and Redis; Celery workers, one queue per kind of work, "
               "run the engines, four of them and the MARCUS model on the GPU.", "".join(b))


def main() -> None:
    for theme in THEMES:
        for name, make in [("hero", hero), ("pipeline", pipeline), ("architecture", architecture)]:
            out = HERE / f"{name}-{theme}.svg"
            out.write_text(make(theme))
            print(f"{out.relative_to(HERE.parents[2])}  {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
