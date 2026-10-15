#!/usr/bin/env python3
"""skinmaker: generate a basic osu! skin (.osk) from a few options.

Pure Python standard library: no pip, no root, no Pillow.
Example:  python3 skinmaker.py MySkin --author me --preset neon
          python3 skinmaker.py --gui      (opens a form in your browser)
"""
import argparse, io, json, math, os, struct, sys, zipfile, zlib

PRESETS = {
    "classic": ["#ffc000", "#00ca00", "#127cff", "#f21839"],
    "neon":    ["#ff2e88", "#2ee6ff", "#b6ff2e", "#ffd02e"],
    "pastel":  ["#ffb3c7", "#b3d9ff", "#c9ffb3", "#fff0b3"],
    "dark":    ["#8a5cff", "#00c2a8", "#ff6b6b", "#ffa94d"],
}

def hexrgb(s):
    s = s.strip().lstrip("#")
    if len(s) != 6: sys.exit(f"Bad color '{s}': use 6 digit hex like ff2e88")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))

# ---------- tiny anti-aliased rasterizer ----------
def cov(d):  # signed distance in px -> coverage 0..1
    return 0.0 if d > 0.5 else 1.0 if d < -0.5 else 0.5 - d

def disc(cx, cy, r):
    return lambda x, y: cov(math.hypot(x - cx, y - cy) - r)

def ring(cx, cy, r, w):
    return lambda x, y: cov(abs(math.hypot(x - cx, y - cy) - r) - w / 2)

def capsule(x1, y1, x2, y2, w):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    def f(x, y):
        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / L)) if L else 0
        return cov(math.hypot(x - x1 - t * dx, y - y1 - t * dy) - w / 2)
    return f

def union(fns):
    return lambda x, y: max(f(x, y) for f in fns)

def render(w, h, layers):
    """layers: list of (shape_fn, (r,g,b,a)), drawn bottom to top. Returns PNG bytes."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            r = g = b = a = 0.0
            for fn, c in layers:
                k = fn(x + 0.5, y + 0.5)
                if k <= 0: continue
                ca = k * c[3] / 255
                r = c[0] * ca + r * (1 - ca)
                g = c[1] * ca + g * (1 - ca)
                b = c[2] * ca + b * (1 - ca)
                a = ca + a * (1 - ca)
            if a > 0:
                raw += bytes(min(255, int(v / a + .5)) for v in (r, g, b)) + bytes([int(a * 255 + .5)])
            else:
                raw += b"\0\0\0\0"
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))

# ---------- seven segment digits ----------
SEGS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
        "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg"}
DW, DH, DT = 56, 88, 10  # digit canvas (@2x) and stroke thickness

def digit_shapes(ch, ox=0):
    xl, xr, yt, ym, yb = ox + DT, ox + DW - DT, DT, DH // 2, DH - DT
    pts = {"a": (xl, yt, xr, yt), "b": (xr, yt, xr, ym), "c": (xr, ym, xr, yb),
           "d": (xl, yb, xr, yb), "e": (xl, ym, xl, yb), "f": (xl, yt, xl, ym),
           "g": (xl, ym, xr, ym)}
    return [capsule(*pts[s], DT) for s in SEGS[ch]]

def text_png(s, color):
    shapes = []
    for i, ch in enumerate(s):
        shapes += digit_shapes(ch, i * (DW + 6))
    return render(len(s) * (DW + 6) - 6, DH, [(union(shapes), color + (255,))])

# ---------- skin assets ----------
def build(a):
    combos = [hexrgb(c) for c in (a.colors.split(",") if a.colors else PRESETS[a.preset])]
    ringc, curc = hexrgb(a.ring), hexrgb(a.cursor)
    W = (255, 255, 255, 255)
    f = {}

    f["hitcircle@2x.png"] = render(256, 256, [(disc(128, 128, 118), W)])
    f["hitcircleoverlay@2x.png"] = render(256, 256, [(ring(128, 128, 118, 12), ringc + (255,))])
    f["approachcircle@2x.png"] = render(256, 256, [(ring(128, 128, 122, 8), W)])

    f["cursor@2x.png"] = render(128, 128, [(ring(64, 64, 52, 10), curc + (255,)),
                                           (disc(64, 64, 12), curc + (255,))])
    f["cursortrail@2x.png"] = render(64, 64, [(disc(32, 32, 28), curc + (40,)),
                                              (disc(32, 32, 20), curc + (90,)),
                                              (disc(32, 32, 11), curc + (170,))])

    f["sliderb0@2x.png"] = render(256, 256, [(disc(128, 128, 100), (255, 255, 255, 70)),
                                             (ring(128, 128, 112, 12), ringc + (255,))])
    f["sliderfollowcircle@2x.png"] = render(512, 512, [(ring(256, 256, 240, 8), (255, 255, 255, 170))])

    for d in "0123456789":
        f[f"default-{d}@2x.png"] = text_png(d, (255, 255, 255))

    f["hit300@2x.png"] = text_png("300", (79, 195, 255))
    f["hit100@2x.png"] = text_png("100", (123, 255, 79))
    f["hit50@2x.png"] = text_png("50", (255, 179, 0))
    f["hit0@2x.png"] = render(96, 96, [(union([capsule(18, 18, 78, 78, 14),
                                               capsule(78, 18, 18, 78, 14)]), (255, 64, 64, 255))])

    ini = ["[General]", f"Name: {a.name}", f"Author: {a.author}", "Version: 2.5",
           "CursorCentre: 1", "AllowSliderBallTint: 1", "", "[Colours]"]
    for i, c in enumerate(combos[:8], 1):
        ini.append(f"Combo{i}: {c[0]},{c[1]},{c[2]}")
    ini += [f"SliderBorder: {ringc[0]},{ringc[1]},{ringc[2]}", "",
            "[Fonts]", "HitCirclePrefix: default", "HitCircleOverlap: 6", ""]
    f["skin.ini"] = "\r\n".join(ini).encode()
    return f

def make_osk(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in files.items(): z.writestr(n, data)
    return buf.getvalue()

def safe_name(n):
    return "".join(ch for ch in n if ch not in '\\/:*?"<>|') or "skin"

PAGE = """<!doctype html><meta charset=utf-8><title>osu! Skin Maker</title>
<style>body{font:16px system-ui,sans-serif;max-width:460px;margin:40px auto;padding:0 16px}
label{display:block;margin:14px 0 4px}input[type=text],select{width:100%;padding:8px;box-sizing:border-box}
.row{display:flex;gap:10px}.row input{flex:1;height:40px}button{margin-top:22px;padding:12px 20px;font-size:16px}
small{color:#777}</style>
<h2>osu! Skin Maker</h2>
<form method=post action=/build>
<label>Skin name</label><input type=text name=name value="My Skin">
<label>Author</label><input type=text name=author value="">
<label>Combo preset</label><select id=preset></select>
<label>Combo colors</label><div class=row>
<input type=color name=c1 id=c1><input type=color name=c2 id=c2><input type=color name=c3 id=c3><input type=color name=c4 id=c4></div>
<label>Circle outline</label><input type=color name=ring value="#ffffff" style="width:100%;height:40px">
<label>Cursor</label><input type=color name=cursor value="#ffffff" style="width:100%;height:40px">
<button>Download .osk</button> <small>takes a few seconds</small></form>
<script>const P=__PRESETS__,s=document.getElementById("preset");
for(const k in P)s.add(new Option(k,k));
function ap(){P[s.value].forEach((c,i)=>document.getElementById("c"+(i+1)).value=c)}
s.onchange=ap;s.value="neon";ap();</script>"""

def gui():
    import http.server, threading, urllib.parse, webbrowser

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body, ctype, extra=()):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in extra: self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            page = PAGE.replace("__PRESETS__", json.dumps(PRESETS))
            self._send(page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            q = urllib.parse.parse_qs(self.rfile.read(n).decode())
            g = lambda k, d="": (q.get(k, [d])[0] or d)
            a = argparse.Namespace(
                name=g("name", "My Skin"), author=g("author", "Unknown"), preset="classic",
                colors=",".join(g(f"c{i}", "#ffffff").lstrip("#") for i in range(1, 5)),
                ring=g("ring", "#ffffff"), cursor=g("cursor", "#ffffff"))
            fn = urllib.parse.quote(safe_name(a.name)) + ".osk"
            self._send(make_osk(build(a)), "application/octet-stream",
                       [("Content-Disposition", f"attachment; filename*=UTF-8''{fn}")])

        def log_message(self, *args): pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print("osu! Skin Maker running at", url, "(Ctrl+C to quit)")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

def main():
    p = argparse.ArgumentParser(description="Generate a basic osu! skin.")
    p.add_argument("name", nargs="?", help="skin name")
    p.add_argument("--gui", action="store_true", help="open the skin maker in your browser")
    p.add_argument("--author", default="Unknown")
    p.add_argument("--preset", choices=PRESETS, default="classic", help="combo color preset")
    p.add_argument("--colors", help="custom combo colors, comma separated hex, e.g. ff0000,00ff00")
    p.add_argument("--ring", default="ffffff", help="circle outline color (hex)")
    p.add_argument("--cursor", default="ffffff", help="cursor color (hex)")
    p.add_argument("--folder", action="store_true", help="write an unzipped folder instead of .osk")
    p.add_argument("--out", default=".", help="output directory")
    a = p.parse_args()
    if a.gui or not a.name:
        return gui()

    files = build(a)
    os.makedirs(a.out, exist_ok=True)
    safe = safe_name(a.name)
    if a.folder:
        d = os.path.join(a.out, safe)
        os.makedirs(d, exist_ok=True)
        for n, data in files.items():
            open(os.path.join(d, n), "wb").write(data)
        print("Wrote folder", d)
    else:
        path = os.path.join(a.out, safe + ".osk")
        open(path, "wb").write(make_osk(files))
        print("Wrote", path)

if __name__ == "__main__":
    main()
