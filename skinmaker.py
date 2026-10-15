#!/usr/bin/env python3
"""osu! Skin Maker: design an osu! skin with a live preview and export it as an .osk.

Pure Python standard library (no pip, no root). One renderer draws both the preview and
the real skin images, so what you see is what you get.

  skinmaker                      open the app window
  skinmaker --browser            open in a normal browser tab instead
  skinmaker "My Skin" --preset neon --set cursor_style=arrow     (no window, writes My Skin.osk)
  skinmaker --list-options       show every customizable option
"""
import argparse, hashlib, http.server, io, json, math, os, re, shutil, socketserver
import subprocess, sys, threading, time, urllib.parse, webbrowser, zipfile, zlib, struct

APP = "osu! Skin Maker"
DATA = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "osu-skinmaker")
LIB = os.path.join(DATA, "skins")

# ======================================================================================
#  Options (single source of truth for the UI, the CLI and the renderer)
# ======================================================================================
def F(k, l, t, d, **kw):
    return dict(k=k, l=l, t=t, d=d, **kw)

SCHEMA = [
    {"g": "Hit circle", "f": [
        F("circle_style", "Fill style", "select", "solid", o=["solid", "gradient", "hollow"]),
        F("circle_fill", "Fill color", "color", "#ffffff"),
        F("circle_outline", "Outline color", "color", "#ffffff"),
        F("circle_outline_w", "Outline width", "range", 12, min=0, max=30),
        F("number_color", "Number color", "color", "#ffffff"),
        F("number_weight", "Number thickness", "range", 10, min=4, max=18),
        F("number_overlap", "Number spacing", "range", 6, min=-6, max=24)]},
    {"g": "Approach circle", "f": [
        F("approach_w", "Thickness", "range", 8, min=2, max=20)]},
    {"g": "Cursor", "f": [
        F("cursor_style", "Shape", "select", "ring", o=["ring", "dot", "cross", "diamond", "arrow"]),
        F("cursor_color", "Color", "color", "#ffffff"),
        F("cursor_size", "Size", "range", 52, min=24, max=70),
        F("cursor_weight", "Thickness", "range", 10, min=4, max=18),
        F("cursor_rotate", "Rotate when moving", "bool", False),
        F("cursor_expand", "Grow when clicking", "bool", True)]},
    {"g": "Cursor trail", "f": [
        F("trail_style", "Style", "select", "glow", o=["glow", "dot", "none"]),
        F("trail_color", "Color", "color", "#ffffff"),
        F("trail_size", "Size", "range", 28, min=8, max=30)]},
    {"g": "Slider", "f": [
        F("ball_color", "Ball color", "color", "#ffffff"),
        F("ball_ring_w", "Ball ring width", "range", 12, min=0, max=24),
        F("follow_w", "Follow circle width", "range", 8, min=2, max=20),
        F("slider_border", "Border color", "color", "#ffffff"),
        F("slider_track_on", "Use a track color", "bool", False),
        F("slider_track", "Track color", "color", "#1b1b26")]},
    {"g": "Hit results", "f": [
        F("hit300_color", "300", "color", "#4fc3ff"),
        F("hit100_color", "100", "color", "#7bff4f"),
        F("hit50_color", "50", "color", "#ffb300"),
        F("hit0_color", "Miss", "color", "#ff4040")]},
]

PRESETS = {
    "classic": {"combos": ["#ffc000", "#00ca00", "#127cff", "#f21839"]},
    "neon": {"combos": ["#ff2e88", "#2ee6ff", "#b6ff2e", "#ffd02e"], "circle_outline": "#ff2e88",
             "cursor_color": "#2ee6ff", "trail_color": "#2ee6ff", "ball_color": "#2ee6ff",
             "slider_border": "#ff2e88", "cursor_style": "ring"},
    "pastel": {"combos": ["#ffb3c7", "#b3d9ff", "#c9ffb3", "#fff0b3"], "circle_style": "gradient",
               "circle_outline": "#ffffff", "cursor_color": "#ffb3c7", "trail_color": "#ffb3c7",
               "ball_color": "#b3d9ff", "slider_border": "#ffffff"},
    "dark": {"combos": ["#8a5cff", "#00c2a8", "#ff6b6b", "#ffa94d"], "circle_style": "gradient",
             "circle_outline": "#d9d9ff", "cursor_style": "diamond", "cursor_color": "#d9d9ff",
             "trail_color": "#8a5cff", "slider_border": "#d9d9ff", "slider_track_on": True,
             "slider_track": "#15121f"},
    "sunset": {"combos": ["#ff7e5f", "#feb47b", "#ff4f81", "#ffd166"], "circle_outline": "#fff1e6",
               "cursor_style": "arrow", "cursor_color": "#fff1e6", "trail_style": "dot",
               "trail_color": "#ff7e5f", "ball_color": "#ffd166", "slider_border": "#fff1e6"},
    "mono": {"combos": ["#ffffff", "#c8c8c8", "#9a9a9a", "#6e6e6e"], "circle_style": "hollow",
             "circle_outline_w": 8, "cursor_style": "cross", "cursor_weight": 6, "trail_style": "none",
             "slider_border": "#ffffff"},
}

DEFAULTS = {"name": "My Skin", "author": "", "combos": list(PRESETS["classic"]["combos"])}
for _g in SCHEMA:
    for _f in _g["f"]:
        DEFAULTS[_f["k"]] = _f["d"]

def hexrgb(s):
    s = str(s).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", s):
        raise ValueError(f"bad color '{s}' (use 6 digit hex like ff2e88)")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))

def hexstr(rgb):
    return "#%02x%02x%02x" % tuple(rgb)

def norm(cfg):
    """Validate/clamp a config dict. Unknown or bad values fall back to defaults."""
    out = json.loads(json.dumps(DEFAULTS))
    cfg = cfg or {}
    for g in SCHEMA:
        for f in g["f"]:
            k, v, t = f["k"], cfg.get(f["k"], f["d"]), f["t"]
            try:
                if t == "color": v = hexstr(hexrgb(v))
                elif t == "range": v = max(f["min"], min(f["max"], int(round(float(v)))))
                elif t == "select": v = v if v in f["o"] else f["d"]
                elif t == "bool": v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
            except (ValueError, TypeError):
                v = f["d"]
            out[k] = v
    combos = []
    for c in (cfg.get("combos") or []):
        try: combos.append(hexstr(hexrgb(c)))
        except ValueError: pass
    out["combos"] = combos[:8] or out["combos"]
    out["name"] = (str(cfg.get("name") or DEFAULTS["name"]))[:60]
    out["author"] = (str(cfg.get("author") or ""))[:60]
    return out

# ======================================================================================
#  Tiny anti-aliased rasterizer.  A layer is (shape_fn, color, bbox).
#  shape_fn(x, y, e) -> coverage 0..1, where e = output pixels per design unit.
#  color is (r,g,b,a) or a function (x,y)->(r,g,b,a).  Everything is designed at @2x.
# ======================================================================================
def cov(d):  # d is a signed distance in OUTPUT pixels
    return 0.0 if d > 0.5 else 1.0 if d < -0.5 else 0.5 - d

M = 4  # bbox margin in design units (room for anti-aliasing)

def disc(cx, cy, r, col):
    return (lambda x, y, e: cov((math.hypot(x - cx, y - cy) - r) * e), col, (cx - r - M, cy - r - M, cx + r + M, cy + r + M))

def ring(cx, cy, r, w, col):
    return (lambda x, y, e: cov((abs(math.hypot(x - cx, y - cy) - r) - w / 2) * e), col,
            (cx - r - w / 2 - M, cy - r - w / 2 - M, cx + r + w / 2 + M, cy + r + w / 2 + M))

def capsule(x1, y1, x2, y2, w, col):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    def f(x, y, e):
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L)) if L else 0.0
        return cov((math.hypot(x - x1 - t * dx, y - y1 - t * dy) - w / 2) * e)
    h = w / 2 + M
    return (f, col, (min(x1, x2) - h, min(y1, y2) - h, max(x1, x2) + h, max(y1, y2) + h))

def poly(pts, col):
    n = len(pts)
    def f(x, y, e):
        best, inside = 1e9, False
        for i in range(n):
            ax, ay = pts[i]; bx, by = pts[(i + 1) % n]
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                inside = not inside
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L)) if L else 0.0
            best = min(best, math.hypot(x - ax - t * dx, y - ay - t * dy))
        return cov((-best if inside else best) * e)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (f, col, (min(xs) - M, min(ys) - M, max(xs) + M, max(ys) + M))

def rrect(x0, y0, x1, y1, r, col):
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 - r, (y1 - y0) / 2 - r
    def f(x, y, e):
        qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
        d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
        return cov(d * e)
    return (f, col, (x0 - M, y0 - M, x1 + M, y1 + M))

def merge(layers, col):
    """Union several shapes into one layer so translucent overlaps don't double up."""
    if not layers: return []
    fns = [l[0] for l in layers]
    bb = (min(l[2][0] for l in layers), min(l[2][1] for l in layers),
          max(l[2][2] for l in layers), max(l[2][3] for l in layers))
    return [(lambda x, y, e: max(f(x, y, e) for f in fns), col, bb)]

def mapcol(layers, g):
    return [(fn, (lambda c: lambda x, y: g(c(x, y)))(col) if callable(col) else g(col), bb) for fn, col, bb in layers]

def tint(layers, rgb):
    return mapcol(layers, lambda c: (c[0] * rgb[0] // 255, c[1] * rgb[1] // 255, c[2] * rgb[2] // 255, c[3]))

def fade(layers, a):
    return mapcol(layers, lambda c: (c[0], c[1], c[2], int(c[3] * a)))

def place(layers, dx, dy, k=1.0):
    """Move local (0,0) to (dx,dy) and scale by k."""
    out = []
    for fn, col, (x0, y0, x1, y1) in layers:
        f = (lambda fn: lambda x, y, e: fn((x - dx) / k, (y - dy) / k, e * k))(fn)
        c = (lambda col: lambda x, y: col((x - dx) / k, (y - dy) / k))(col) if callable(col) else col
        out.append((f, c, (x0 * k + dx, y0 * k + dy, x1 * k + dx, y1 * k + dy)))
    return out

def put(layers, cx, cy, cw, ch, k=1.0):
    """Centre a cw x ch sprite on (cx,cy)."""
    return place(layers, cx - cw * k / 2, cy - ch * k / 2, k)

def png_bytes(w, h, rows):
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))

def render(w, h, layers, scale=1.0, bg=None):
    n = w * h
    if bg: R, G, B, A = [float(bg[0])] * n, [float(bg[1])] * n, [float(bg[2])] * n, [1.0] * n
    else: R, G, B, A = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
    for fn, col, (x0, y0, x1, y1) in layers:
        px0, px1 = max(0, int(math.floor(x0 * scale))), min(w, int(math.ceil(x1 * scale)))
        py0, py1 = max(0, int(math.floor(y0 * scale))), min(h, int(math.ceil(y1 * scale)))
        dyn = callable(col)
        for py in range(py0, py1):
            y = (py + 0.5) / scale
            base = py * w
            for px in range(px0, px1):
                x = (px + 0.5) / scale
                k = fn(x, y, scale)
                if k <= 0: continue
                c = col(x, y) if dyn else col
                ca = k * c[3] / 255
                i = base + px
                ia = 1 - ca
                R[i] = c[0] * ca + R[i] * ia
                G[i] = c[1] * ca + G[i] * ia
                B[i] = c[2] * ca + B[i] * ia
                A[i] = ca + A[i] * ia
    raw = bytearray()
    for py in range(h):
        raw.append(0)
        for i in range(py * w, py * w + w):
            a = A[i]
            if a > 0:
                raw += bytes((min(255, int(R[i] / a + .5)), min(255, int(G[i] / a + .5)),
                              min(255, int(B[i] / a + .5)), int(a * 255 + .5)))
            else:
                raw += b"\0\0\0\0"
    return png_bytes(w, h, bytes(raw))

# ======================================================================================
#  Skin elements (all @2x design units)
# ======================================================================================
CR = 118  # hit circle radius; sprites are 256x256, centre (128,128)

SEGS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
        "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg"}
DW, DH, GAP = 56, 88, 6

def text_layers(s, col, T=10):
    m = T / 2 + 1
    caps = []
    for i, ch in enumerate(s):
        x0 = i * (DW + GAP)
        xl, xr, yt, ym, yb = x0 + m, x0 + DW - m, m, DH / 2, DH - m
        P = {"a": (xl, yt, xr, yt), "b": (xr, yt, xr, ym), "c": (xr, ym, xr, yb), "d": (xl, yb, xr, yb),
             "e": (xl, ym, xl, yb), "f": (xl, yt, xl, ym), "g": (xl, ym, xr, ym)}
        if ch == "1":
            caps.append(capsule(x0 + DW / 2, yt, x0 + DW / 2, yb, T, col))
        else:
            caps += [capsule(*P[sg], T, col) for sg in SEGS[ch]]
    return merge(caps, col)

def text_size(s):
    return len(s) * DW + (len(s) - 1) * GAP, DH

def el_hitcircle(c):
    fill, w = hexrgb(c["circle_fill"]), c["circle_outline_w"]
    r = CR - w / 2 + 1 if w else CR
    st = c["circle_style"]
    if st == "solid": col = fill + (255,)
    elif st == "hollow": col = fill + (40,)
    else:
        col = lambda x, y: tuple(int(v * (1 - 0.35 * min(1.0, math.hypot(x - 128, y - 128) / CR))) for v in fill) + (255,)
    return [disc(128, 128, r, col)]

def el_overlay(c):
    w = c["circle_outline_w"]
    return [ring(128, 128, CR - w / 2, w, hexrgb(c["circle_outline"]) + (255,))] if w else []

def el_approach(c):
    w = c["approach_w"]
    return [ring(128, 128, 124 - w / 2, w, (255, 255, 255, 255))]

CUR = 160  # cursor sprite size

def cursor_hot(c):
    return (14, 14) if c["cursor_style"] == "arrow" else (CUR / 2, CUR / 2)

def el_cursor(c):
    col, R, T, st = hexrgb(c["cursor_color"]) + (255,), c["cursor_size"], c["cursor_weight"], c["cursor_style"]
    m = CUR / 2
    if st == "ring":
        return [ring(m, m, R, T, col), disc(m, m, max(T * 0.9, 5), col)]
    if st == "dot":
        return [disc(m, m, R * 0.5, col)]
    if st == "cross":
        return merge([capsule(m - R, m, m + R, m, T, col), capsule(m, m - R, m, m + R, T, col)], col)
    if st == "diamond":
        p = [(m, m - R), (m + R, m), (m, m + R), (m - R, m)]
        return merge([capsule(*p[i], *p[(i + 1) % 4], T, col) for i in range(4)], col) + [disc(m, m, max(T * 0.7, 4), col)]
    s = R / 52.0
    pts = [(14, 14), (14, 14 + 84 * s), (14 + 22 * s, 14 + 64 * s), (14 + 40 * s, 14 + 92 * s),
           (14 + 54 * s, 14 + 84 * s), (14 + 36 * s, 14 + 58 * s), (14 + 62 * s, 14 + 58 * s)]
    edge = [capsule(*pts[i], *pts[(i + 1) % len(pts)], 5, (0, 0, 0, 170)) for i in range(len(pts))]
    return [poly(pts, col)] + merge(edge, (0, 0, 0, 170))

def el_trail(c):
    col, R, st = hexrgb(c["trail_color"]), c["trail_size"], c["trail_style"]
    if st == "none": return []
    if st == "dot": return [disc(32, 32, R * 0.55, col + (210,))]
    return [disc(32, 32, R, col + (40,)), disc(32, 32, R * 0.72, col + (90,)), disc(32, 32, R * 0.4, col + (170,))]

def el_ball(c):
    col, w = hexrgb(c["ball_color"]), c["ball_ring_w"]
    out = [disc(128, 128, 100, col + (70,))]
    if w: out.append(ring(128, 128, CR - w / 2, w, col + (255,)))
    return out

def el_follow(c):
    return [ring(256, 256, 240, c["follow_w"], hexrgb(c["ball_color"]) + (170,))]

def sprite_text(s, col):
    w, h = text_size(s)
    return w + 8, h + 8, place(text_layers(s, col + (255,)), 4, 4)

def build_files(c):
    """Return {filename: bytes} for the whole skin."""
    c = norm(c)
    f = {}
    f["hitcircle@2x.png"] = render(256, 256, el_hitcircle(c))
    f["hitcircleoverlay@2x.png"] = render(256, 256, el_overlay(c))
    f["approachcircle@2x.png"] = render(256, 256, el_approach(c))
    f["cursor@2x.png"] = render(CUR, CUR, el_cursor(c))
    f["cursortrail@2x.png"] = render(64, 64, el_trail(c)) if c["trail_style"] != "none" else render(1, 1, [])
    f["sliderb0@2x.png"] = render(256, 256, el_ball(c))
    f["sliderfollowcircle@2x.png"] = render(512, 512, el_follow(c))
    ncol = hexrgb(c["number_color"]) + (255,)
    for d in "0123456789":
        f[f"default-{d}@2x.png"] = render(DW, DH, text_layers(d, ncol, c["number_weight"]))
    for key, s in (("hit300", "300"), ("hit100", "100"), ("hit50", "50")):
        w, h, lay = sprite_text(s, hexrgb(c[key + "_color"]))
        f[key + "@2x.png"] = render(w, h, lay)
    x = hexrgb(c["hit0_color"]) + (255,)
    f["hit0@2x.png"] = render(96, 96, merge([capsule(18, 18, 78, 78, 14, x), capsule(78, 18, 18, 78, 14, x)], x))
    f["skin.ini"] = skin_ini(c)
    return f

def skin_ini(c):
    ini = ["[General]", f"Name: {c['name']}", f"Author: {c['author'] or 'Unknown'}", "Version: 2.5",
           f"CursorCentre: {0 if c['cursor_style'] == 'arrow' else 1}",
           f"CursorRotate: {int(c['cursor_rotate'])}", f"CursorExpand: {int(c['cursor_expand'])}",
           "AllowSliderBallTint: 1", "", "[Colours]"]
    for i, h in enumerate(c["combos"], 1):
        r = hexrgb(h); ini.append(f"Combo{i}: {r[0]},{r[1]},{r[2]}")
    b = hexrgb(c["slider_border"]); ini.append(f"SliderBorder: {b[0]},{b[1]},{b[2]}")
    if c["slider_track_on"]:
        t = hexrgb(c["slider_track"]); ini.append(f"SliderTrackOverride: {t[0]},{t[1]},{t[2]}")
    ini += ["", "[Fonts]", "HitCirclePrefix: default", f"HitCircleOverlap: {c['number_overlap']}", ""]
    return "\r\n".join(ini).encode()

def make_osk(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items(): z.writestr(n, d)
    return buf.getvalue()

def safe_name(n):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", n).strip() or "skin"

# ======================================================================================
#  Preview scenes
# ======================================================================================
BGS = {"dark": (22, 22, 29), "light": (233, 233, 239), "mid": (96, 96, 110)}

def circle_stack(c, cx, cy, number, combo, approach_k=None):
    out = tint(put(el_hitcircle(c), cx, cy, 256, 256), combo)
    out += put(el_overlay(c), cx, cy, 256, 256)
    w, h = text_size(number)
    out += put(text_layers(number, hexrgb(c["number_color"]) + (255,), c["number_weight"]), cx, cy, w, h)
    if approach_k:
        out += tint(put(el_approach(c), cx, cy, 256, 256, approach_k), combo)
    return out

def scene_layers(c):
    cb = [hexrgb(h) for h in c["combos"]]
    co = lambda i: cb[i % len(cb)]
    border = hexrgb(c["slider_border"])
    track = hexrgb(c["slider_track"]) if c["slider_track_on"] else tuple(int(v * 0.3) for v in co(2))
    L = []
    # slider body, head circle, ball + follow circle
    L += [capsule(800, 260, 1100, 260, 236, border + (255,)), capsule(800, 260, 1100, 260, 212, track + (255,))]
    L += circle_stack(c, 800, 260, "3", co(2))
    L += put(el_follow(c), 990, 260, 512, 512, 0.62)
    L += put(el_ball(c), 990, 260, 256, 256)
    # circles
    L += circle_stack(c, 520, 400, "2", co(1), 1.75)
    L += circle_stack(c, 250, 230, "1", co(0), 1.4)
    # hit results
    for key, s, x in (("hit300", "300", 150), ("hit100", "100", 400), ("hit50", "50", 640)):
        w, h, lay = sprite_text(s, hexrgb(c[key + "_color"]))
        L += put(lay, x, 640, w, h)
    xc = hexrgb(c["hit0_color"]) + (255,)
    L += put(merge([capsule(18, 18, 78, 78, 14, xc), capsule(78, 18, 18, 78, 14, xc)], xc), 800, 640, 96, 96)
    # trail + cursor
    tx, ty = 1010, 560
    for i in range(7):
        t = i / 6
        L += fade(put(el_trail(c), 840 + (tx - 840) * t, 650 + (ty - 650) * t, 64, 64), 0.15 + 0.85 * t)
    hx, hy = cursor_hot(c)
    L += place(el_cursor(c), tx - hx, ty - hy)
    return L

def cursor_layers(c):
    L = []
    px, py, k = 250, 150, 1.8
    hx, hy = cursor_hot(c)
    for i in range(6):
        t = i / 5
        L += fade(put(el_trail(c), 70 + (px - 70) * t, 230 + (py - 230) * t, 64, 64, k), 0.15 + 0.85 * t)
    L += place(el_cursor(c), px - hx * k, py - hy * k, k)
    return L

def preview_png(cfg, view="scene", scale=0.5, bg="dark"):
    c = norm(cfg)
    back = BGS.get(bg, BGS["dark"])
    if view == "cursor": return render(400, 300, cursor_layers(c), 1.0, back)
    s = 0.15 if view == "thumb" else max(0.2, min(2.0, float(scale)))
    return render(int(1280 * s), int(720 * s), scene_layers(c), s, back)

def icon_png(size=256):
    g = lambda x, y: (int(255 + (122 - 255) * y / 256), int(79 + (77 - 79) * y / 256), int(154 + (255 - 154) * y / 256), 255)
    L = [rrect(8, 8, 248, 248, 56, g)]
    L += [ring(124, 120, 70, 16, (255, 255, 255, 255))]
    L += put(text_layers("1", (255, 255, 255, 255), 14), 124, 120, DW, DH, 0.85)
    pts = [(150, 150), (150, 150 + 66), (150 + 17, 150 + 50), (150 + 31, 150 + 72), (150 + 42, 150 + 66), (150 + 28, 150 + 46), (150 + 48, 150 + 46)]
    L += [poly(pts, (255, 255, 255, 255))] + merge([capsule(*pts[i], *pts[(i + 1) % 7], 4, (40, 20, 80, 200)) for i in range(7)], (40, 20, 80, 200))
    s = size / 256.0
    return render(size, size, L, s)

# ======================================================================================
#  The app (local web server + window)
# ======================================================================================
PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>osu! Skin Maker</title>
<link rel=icon href=/icon.png><meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{color-scheme:light dark;--bg:#f4f4f8;--pn:#fff;--tx:#1d1d26;--mu:#76768a;--bd:#dcdce6;--ac:#e8387f;--ac2:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#14141b;--pn:#1d1d27;--tx:#ececf4;--mu:#8d8da2;--bd:#2e2e3d;--ac:#ff4f9a}}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{font:14px system-ui,sans-serif;background:var(--bg);color:var(--tx);display:flex;flex-direction:column}
header{display:flex;gap:10px;align-items:center;padding:10px 14px;background:var(--pn);border-bottom:1px solid var(--bd);flex-wrap:wrap}
header img{width:30px;height:30px;border-radius:8px}header b{font-size:15px;margin-right:6px}
input[type=text],select{padding:7px 9px;border:1px solid var(--bd);border-radius:8px;background:var(--bg);color:var(--tx);font:inherit}
button{padding:7px 12px;border:1px solid var(--bd);border-radius:8px;background:var(--pn);color:var(--tx);font:inherit;cursor:pointer}
button.p{background:var(--ac);border-color:var(--ac);color:var(--ac2);font-weight:600}
main{flex:1;display:grid;grid-template-columns:210px 1fr 330px;min-height:0}
aside,section{overflow:auto;padding:12px}aside{background:var(--pn);border-right:1px solid var(--bd)}
#side2{background:var(--pn);border-left:1px solid var(--bd)}
h3{margin:2px 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mu)}
.card{display:flex;flex-direction:column;gap:4px;position:relative;margin-bottom:10px;padding:6px;border:1px solid var(--bd);border-radius:10px;cursor:pointer}
.card:hover{border-color:var(--ac)}.card img{width:100%;border-radius:6px;background:#222;min-height:40px}
.card button{position:absolute;top:8px;right:8px;padding:0 7px;line-height:20px}
.muted{color:var(--mu)}
.view{display:flex;flex-direction:column;gap:14px;align-items:center}
.view img{max-width:100%;border-radius:12px;border:1px solid var(--bd);background:#222}
.cap{align-self:flex-start;color:var(--mu);font-size:12px}
details{border:1px solid var(--bd);border-radius:10px;margin-bottom:10px;padding:2px 10px}
summary{cursor:pointer;font-weight:600;padding:8px 0}
.row{display:grid;grid-template-columns:1fr auto 120px;gap:8px;align-items:center;padding:5px 0}
.row span{color:var(--mu)}.row b{font-weight:500;min-width:24px;text-align:right}
.row input[type=color]{width:120px;height:28px;padding:0;border:1px solid var(--bd);border-radius:6px;background:none}
.row input[type=range]{width:120px}.row select{width:120px}.row input[type=checkbox]{justify-self:end}
.row:not(:has(b)){grid-template-columns:1fr 120px}
#combos{display:flex;gap:8px;flex-wrap:wrap;padding:4px 0 10px}
.sw{position:relative}.sw input{width:44px;height:44px;border:1px solid var(--bd);border-radius:10px;padding:0;background:none}
.sw button{position:absolute;top:-6px;right:-6px;padding:0 5px;line-height:16px;border-radius:9px;font-size:12px}
.add{width:44px;height:44px;font-size:20px}
#toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:var(--tx);color:var(--bg);padding:9px 16px;border-radius:20px;opacity:0;transition:.2s;pointer-events:none}
#toast.on{opacity:1}#busy{color:var(--mu);font-size:12px}
@media(max-width:900px){main{grid-template-columns:1fr}aside{display:none}}
</style></head><body>
<header><img src=/icon.png><b>osu! Skin Maker</b>
<input type=text id=name placeholder="Skin name" style="width:150px"><input type=text id=author placeholder="Author" style="width:120px">
<select id=preset><option value="">Preset…</option></select>
<select id=bg title="Preview background"><option value=dark>Dark bg</option><option value=mid>Mid bg</option><option value=light>Light bg</option></select>
<span id=busy hidden>rendering…</span><span style="flex:1"></span>
<button id=save>Save to library</button><button id=png>Save preview image</button><button id=dl class=p>Download .osk</button></header>
<main>
<aside><h3>My skins</h3><div id=lib></div></aside>
<section><div class=view>
<div class=cap>Live preview: this is rendered by the same code that writes your skin files.</div>
<img id=scene alt=preview width=640 height=360>
<div class=cap>Cursor close-up (with trail)</div>
<img id=cursor alt=cursor width=400 height=300></div></section>
<aside id=side2><h3>Customize</h3>
<details open><summary>Combo colors</summary><div id=combos></div></details>
<div id=controls></div></aside>
</main><div id=toast></div>
<script>
const $=s=>document.querySelector(s);
let S,cfg,seq=0,timer;const inputs={};
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const clone=o=>JSON.parse(JSON.stringify(o));
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(toast.t);toast.t=setTimeout(()=>t.classList.remove('on'),2600)}
function schedule(){clearTimeout(timer);timer=setTimeout(refresh,150)}
async function show(sel,res){const u=URL.createObjectURL(await res.blob()),im=$(sel);if(im.dataset.u)URL.revokeObjectURL(im.dataset.u);im.dataset.u=u;im.src=u}
async function refresh(){const n=++seq;$('#busy').hidden=false;
  try{const bg=$('#bg').value;const [a,b]=await Promise.all([post('/api/preview',{cfg,view:'scene',scale:.5,bg}),post('/api/preview',{cfg,view:'cursor',bg})]);
  if(n!==seq)return;await show('#scene',a);await show('#cursor',b)}catch(e){}
  if(n===seq)$('#busy').hidden=true}
function set(k,v){cfg[k]=v;schedule()}
function row(f){const w=document.createElement('label');w.className='row';const s=document.createElement('span');s.textContent=f.l;w.append(s);let i;
  if(f.t==='select'){i=document.createElement('select');f.o.forEach(o=>i.add(new Option(o,o)));i.onchange=()=>set(f.k,i.value)}
  else if(f.t==='range'){i=document.createElement('input');i.type='range';i.min=f.min;i.max=f.max;const v=document.createElement('b');i.oninput=()=>{v.textContent=i.value;set(f.k,+i.value)};w.append(v);i._v=v}
  else if(f.t==='bool'){i=document.createElement('input');i.type='checkbox';i.onchange=()=>set(f.k,i.checked)}
  else{i=document.createElement('input');i.type='color';i.oninput=()=>set(f.k,i.value)}
  w.append(i);inputs[f.k]=i;return w}
function combos(){const box=$('#combos');box.innerHTML='';
  cfg.combos.forEach((c,i)=>{const d=document.createElement('div');d.className='sw';const p=document.createElement('input');p.type='color';p.value=c;p.oninput=()=>{cfg.combos[i]=p.value;schedule()};d.append(p);
    if(cfg.combos.length>1){const x=document.createElement('button');x.textContent='×';x.title='Remove';x.onclick=()=>{cfg.combos.splice(i,1);combos();schedule()};d.append(x)}box.append(d)});
  if(cfg.combos.length<8){const a=document.createElement('button');a.textContent='+';a.className='add';a.title='Add combo color';a.onclick=()=>{cfg.combos.push('#ffffff');combos();schedule()};box.append(a)}}
function sync(){for(const k in inputs){const i=inputs[k];if(i.type==='checkbox')i.checked=!!cfg[k];else{i.value=cfg[k];if(i._v)i._v.textContent=cfg[k]}}
  $('#name').value=cfg.name;$('#author').value=cfg.author;combos();schedule()}
async function skins(){const r=await (await fetch('/api/skins')).json(),box=$('#lib');
  box.innerHTML=r.length?'':'<p class=muted>Nothing saved yet. Use "Save to library".</p>';
  for(const s of r){const d=document.createElement('div');d.className='card';const im=document.createElement('img'),t=document.createElement('span'),x=document.createElement('button');
    t.textContent=s.name;x.textContent='×';x.title='Delete';
    d.onclick=()=>{cfg=Object.assign(clone(S.defaults),clone(s.cfg));sync()};
    x.onclick=async e=>{e.stopPropagation();await fetch('/api/skins/'+encodeURIComponent(s.name),{method:'DELETE'});skins()};
    d.append(im,t,x);box.append(d);
    post('/api/preview',{cfg:s.cfg,view:'thumb',bg:$('#bg').value}).then(r=>r.blob()).then(b=>im.src=URL.createObjectURL(b))}}
async function download(path,body,fname){const r=await post(path,body);if(!r.ok){toast('Something went wrong');return false}
  const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download=fname;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000);return true}
$('#dl').onclick=async()=>{toast('Building skin, a few seconds…');if(await download('/api/build',{cfg},(cfg.name||'skin')+'.osk'))toast('Done! Open the .osk with osu!')};
$('#png').onclick=async()=>{toast('Rendering…');await download('/api/preview',{cfg,view:'scene',scale:1,bg:$('#bg').value},(cfg.name||'skin')+'-preview.png')};
$('#save').onclick=async()=>{const r=await post('/api/skins',{cfg});toast(r.ok?'Saved to library':'Could not save');skins()};
$('#name').oninput=e=>{cfg.name=e.target.value};$('#author').oninput=e=>{cfg.author=e.target.value};
$('#bg').onchange=()=>{schedule();skins()};
(async()=>{S=await (await fetch('/api/schema')).json();cfg=clone(S.defaults);
  const host=$('#controls');S.schema.forEach((g,gi)=>{const d=document.createElement('details');d.open=gi<3;const s=document.createElement('summary');s.textContent=g.g;d.append(s);g.f.forEach(f=>d.append(row(f)));host.append(d)});
  const ps=$('#preset');Object.keys(S.presets).forEach(p=>ps.add(new Option(p,p)));
  ps.onchange=()=>{if(ps.value){Object.assign(cfg,clone(S.presets[ps.value]));sync()}};
  sync();skins();setInterval(()=>fetch('/ping'),4000);
  addEventListener('pagehide',()=>navigator.sendBeacon('/api/bye'))})();
</script></body></html>"""

CHROMIUMS = ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser", "brave-browser",
             "microsoft-edge", "microsoft-edge-stable", "vivaldi", "opera"]
FLATPAK_CHROMIUMS = ["com.google.Chrome", "org.chromium.Chromium", "com.brave.Browser", "com.microsoft.Edge",
                     "io.github.ungoogled_software.ungoogled_chromium"]

def launch_app_window(url):
    """Open the UI in a standalone app window (no tabs/address bar). Needs a Chromium based browser."""
    args = [f"--app={url}", "--window-size=1280,820"]
    for b in CHROMIUMS:
        p = shutil.which(b)
        if p:
            subprocess.Popen([p] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True
    if shutil.which("flatpak"):
        try:
            have = subprocess.run(["flatpak", "list", "--app", "--columns=application"], capture_output=True, text=True, timeout=10).stdout.split()
        except Exception:
            have = []
        for b in FLATPAK_CHROMIUMS:
            if b in have:
                subprocess.Popen(["flatpak", "run", b] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return True
    return False

def lib_path(name):
    return os.path.join(LIB, safe_name(name) + ".json")

def serve(want_app=True):
    state = {"ping": time.time(), "bye": 0.0}
    cache, lock = {}, threading.Lock()

    class H(http.server.BaseHTTPRequestHandler):
        def _out(self, body, ctype, code=200, extra=()):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in extra: self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._out(json.dumps(obj).encode(), "application/json", code)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            try: return json.loads(raw.decode() or "{}")
            except ValueError: return {}

        def do_GET(self):
            state["ping"] = time.time()
            path = urllib.parse.urlparse(self.path).path
            if path == "/": self._out(PAGE.encode(), "text/html; charset=utf-8")
            elif path == "/ping": self._out(b"ok", "text/plain")
            elif path == "/icon.png":
                with lock:
                    if "icon" not in cache: cache["icon"] = icon_png(256)
                self._out(cache["icon"], "image/png")
            elif path == "/api/schema":
                self._json({"schema": SCHEMA, "presets": PRESETS, "defaults": DEFAULTS})
            elif path == "/api/skins":
                out = []
                if os.path.isdir(LIB):
                    for fn in sorted(os.listdir(LIB)):
                        if fn.endswith(".json"):
                            try: c = norm(json.load(open(os.path.join(LIB, fn))))
                            except Exception: continue
                            out.append({"name": c["name"], "cfg": c})
                self._json(out)
            else: self._out(b"not found", "text/plain", 404)

        def do_POST(self):
            state["ping"] = time.time()
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/bye":
                state["bye"] = time.time(); self._out(b"", "text/plain"); return
            data = self._body()
            try:
                if path == "/api/preview":
                    view, scale, bg = data.get("view", "scene"), data.get("scale", .5), data.get("bg", "dark")
                    key = hashlib.sha1(json.dumps([norm(data.get("cfg")), view, scale, bg], sort_keys=True).encode()).hexdigest()
                    with lock: png = cache.get(key)
                    if png is None:
                        png = preview_png(data.get("cfg"), view, scale, bg)
                        with lock:
                            if len(cache) > 80: cache.clear()
                            cache[key] = png
                    self._out(png, "image/png")
                elif path == "/api/build":
                    c = norm(data.get("cfg"))
                    fn = urllib.parse.quote(safe_name(c["name"])) + ".osk"
                    self._out(make_osk(build_files(c)), "application/octet-stream",
                              extra=[("Content-Disposition", f"attachment; filename*=UTF-8''{fn}")])
                elif path == "/api/skins":
                    c = norm(data.get("cfg")); os.makedirs(LIB, exist_ok=True)
                    with open(lib_path(c["name"]), "w") as fh: json.dump(c, fh, indent=1)
                    self._json({"ok": True})
                else: self._out(b"not found", "text/plain", 404)
            except Exception as e:
                self._out(str(e).encode(), "text/plain", 500)

        def do_DELETE(self):
            path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            if path.startswith("/api/skins/"):
                try: os.remove(lib_path(path[len("/api/skins/"):]))
                except OSError: pass
                self._json({"ok": True})
            else: self._out(b"not found", "text/plain", 404)

        def log_message(self, *a): pass

    class Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    srv = Srv(("127.0.0.1", 0), H)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    app_mode = want_app and launch_app_window(url)
    if not app_mode:
        webbrowser.open(url)
        print(f"{APP} running at {url}  (press Ctrl+C to quit)")
    else:
        # The window is the app: quit when it closes.
        def watch():
            while True:
                time.sleep(2); now = time.time()
                if state["bye"] and now - state["bye"] > 6 and state["ping"] < state["bye"]: break
                if now - state["ping"] > 180: break
            srv.shutdown()
        threading.Thread(target=watch, daemon=True).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

# ======================================================================================
#  CLI
# ======================================================================================
def main():
    p = argparse.ArgumentParser(description="osu! Skin Maker. Run with no arguments to open the app.")
    p.add_argument("name", nargs="?", help="skin name (skips the app and writes the skin directly)")
    p.add_argument("--browser", action="store_true", help="open in a normal browser tab instead of an app window")
    p.add_argument("--author", default="")
    p.add_argument("--preset", choices=PRESETS, help="start from a preset")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="set any option, e.g. cursor_style=arrow")
    p.add_argument("--colors", help="combo colors, comma separated hex")
    p.add_argument("--ring", help="circle outline color (hex)")
    p.add_argument("--cursor", help="cursor color (hex)")
    p.add_argument("--folder", action="store_true", help="write an unzipped folder instead of an .osk")
    p.add_argument("--out", default=".", help="output directory")
    p.add_argument("--list-options", action="store_true", help="print all options and exit")
    p.add_argument("--make-icon", metavar="PATH", help="write the app icon PNG and exit")
    a = p.parse_args()

    if a.list_options:
        for g in SCHEMA:
            print(f"[{g['g']}]")
            for f in g["f"]:
                extra = "/".join(f["o"]) if f["t"] == "select" else f"{f['min']}..{f['max']}" if f["t"] == "range" else f["t"]
                print(f"  {f['k']:<18} {extra:<34} default: {f['d']}")
        return
    if a.make_icon:
        os.makedirs(os.path.dirname(os.path.abspath(a.make_icon)), exist_ok=True)
        open(a.make_icon, "wb").write(icon_png(256)); print("Wrote", a.make_icon); return
    if not a.name:
        return serve(want_app=not a.browser)

    cfg = json.loads(json.dumps(DEFAULTS))
    if a.preset: cfg.update(PRESETS[a.preset])
    cfg["name"], cfg["author"] = a.name, a.author
    if a.colors: cfg["combos"] = [x.strip() for x in a.colors.split(",")]
    if a.ring: cfg["circle_outline"] = cfg["slider_border"] = a.ring
    if a.cursor: cfg["cursor_color"] = a.cursor
    for kv in a.set:
        if "=" not in kv: sys.exit(f"--set needs KEY=VALUE, got '{kv}'")
        k, v = kv.split("=", 1)
        if k not in DEFAULTS: sys.exit(f"Unknown option '{k}'. Try --list-options")
        cfg[k] = v
    files = build_files(cfg)
    os.makedirs(a.out, exist_ok=True)
    safe = safe_name(a.name)
    if a.folder:
        d = os.path.join(a.out, safe); os.makedirs(d, exist_ok=True)
        for n, data in files.items(): open(os.path.join(d, n), "wb").write(data)
        print("Wrote folder", d)
    else:
        path = os.path.join(a.out, safe + ".osk")
        open(path, "wb").write(make_osk(files)); print("Wrote", path)

if __name__ == "__main__":
    main()
