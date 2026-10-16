"""Validates LLM design tokens and renders CSS locally (no LLM tokens, no CSS injection)."""
import re
from html import escape

DEFAULT = {"colors": {"bg": "#0b0b14", "fg": "#f5f5ff", "primary": "#7c5cff", "accent": "#00d4ff", "muted": "#9a9ab5"},
           "fonts": {"head": "Poppins", "body": "Inter"}}
HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")
FONT = re.compile(r"^[A-Za-z0-9 ]{2,30}$")


def _num(v, lo, hi, d):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return d


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x))) for x in c)


def _lum(c) -> float:
    f = lambda v: (v / 255 / 12.92) if v / 255 <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4    # noqa: E731
    r, g, b = (f(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _toward(c, target, need, against) -> tuple:
    """Move colour c toward target in small steps until it reaches `need` contrast against `against`."""
    for i in range(1, 21):
        t = i / 20
        n = tuple(c[k] + (target[k] - c[k]) * t for k in range(3))
        if contrast(n, against) >= need:
            return n
    return target


SAFE_PRIMARY = "#4f46e5"       # 6.3:1 with the white button label, still visible on light and dark backgrounds


def _readable(colors: dict) -> dict:
    """The app shell draws button/brand-mark labels in white and uses accent/muted as text, so LLM palettes that are
    too pale (white button on a white page, invisible borders) are corrected instead of shipped."""
    bg = _rgb(colors["bg"])
    white, black = (255, 255, 255), (0, 0, 0)
    out = dict(colors)
    fg = _rgb(colors["fg"])
    if contrast(fg, bg) < 4.5:
        fg = white if contrast(white, bg) >= contrast(black, bg) else black
        out["fg"] = _hex(fg)
    pr = _rgb(colors["primary"])
    if contrast(pr, white) < 4.0:
        pr = _toward(pr, black, 4.0, white)
    if contrast(pr, bg) < 1.5:
        pr = _rgb(SAFE_PRIMARY)
    out["primary"] = _hex(pr)
    away = black if _lum(bg) > 0.5 else white                        # direction that increases contrast with the page
    for k, need in (("accent", 3.0), ("muted", 3.5)):
        c = _rgb(colors[k])
        if contrast(c, bg) < need:
            c = _toward(c, away, need, bg)
        out[k] = _hex(c)
    return out


def normalize(d) -> dict:
    d = d if isinstance(d, dict) else {}
    out = {"colors": {}, "fonts": {}}
    for k, dv in DEFAULT["colors"].items():
        v = (d.get("colors") or {}).get(k)
        out["colors"][k] = v if isinstance(v, str) and HEX.match(v) and len(v) in (4, 5, 7, 9) else dv
    out["colors"] = _readable(out["colors"])
    for k, dv in DEFAULT["fonts"].items():
        v = (d.get("fonts") or {}).get(k)
        out["fonts"][k] = v if isinstance(v, str) and FONT.match(v) else dv
    out["radius"] = _num(d.get("radius"), 0, 40, 16)
    out["spacing"] = _num(d.get("spacing"), 4, 12, 8)
    out["style"] = str(d.get("style", ""))[:60]
    return out


def render_tokens(d) -> str:
    d = normalize(d)
    vars_ = "".join(f"--{k}:{v};" for k, v in d["colors"].items())
    return (f":root{{{vars_}--font-head:'{d['fonts']['head']}';--font-body:'{d['fonts']['body']}';"
            f"--radius:{d['radius']}px;--space:{d['spacing']}px;}}\n")


def fonts_link(d) -> str:
    d = normalize(d)
    fam = []
    for f in (d["fonts"]["head"], d["fonts"]["body"]):
        if f not in fam:
            fam.append(f)
    q = "&".join(f"family={f.replace(' ', '+')}:wght@400;600;700" for f in fam)
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">'
            f'<link rel="stylesheet" href="{escape("https://fonts.googleapis.com/css2?" + q + "&display=swap")}">')
