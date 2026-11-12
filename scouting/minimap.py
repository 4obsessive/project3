"""Minimapa: imagen, calibración mundo -> imagen y recalibración por ajuste a la máscara caminable.

Calibración = coordenadas de mundo de las esquinas de la imagen:
    left = (x - x_min) / (x_max - x_min)      (invert_x: 1 - left)
    top  = (y_max - y) / (y_max - y_min)      si invert_y (Y del mundo crece hacia arriba)
La calibración oficial sale de /v1/assets/map: radio 10752 centrado en 0, Y invertida
(verificado con las posiciones mundo/relativas de los campamentos neutrales)."""
import json
import os
import struct
import zlib

from . import config

CALIB_PATH = os.path.join(config.STATIC_DIR, "minimap.json")
IMAGE_PNG = os.path.join(config.STATIC_DIR, "minimap.png")

OFFICIAL = {"x_min": -10752, "x_max": 10752, "y_min": -10752, "y_max": 10752, "invert_y": True, "invert_x": False,
            "source": "oficial (/v1/assets/map: radio 10752, centro 0)"}


def load_calibration():
    if os.path.exists(CALIB_PATH):
        with open(CALIB_PATH, encoding="utf-8") as f:
            return json.load(f)
    return dict(OFFICIAL)


def save_calibration(cal):
    tmp = CALIB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cal, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CALIB_PATH)


def official_from_asset(asset):
    r = float(asset.get("radius") or 10752)
    cal = dict(OFFICIAL)
    cal.update({"x_min": -r, "x_max": r, "y_min": -r, "y_max": r})
    return cal


def world_to_rel(cal, x, y):
    u = (x - cal["x_min"]) / (cal["x_max"] - cal["x_min"])
    v = (y - cal["y_min"]) / (cal["y_max"] - cal["y_min"])
    if cal.get("invert_x"):
        u = 1 - u
    if cal.get("invert_y", True):
        v = 1 - v
    return u, v


# ----------------------------------------------------------- PNG (stdlib)
def read_png_alpha(path):
    """Devuelve (ancho, alto, bytearray de alpha). Soporta PNG 8 bits RGBA/GA/RGB/gris, sin entrelazado."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("No es un PNG")
    pos, idat, w = 8, [], None
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or interlace:
                raise ValueError("PNG no soportado (solo 8 bits sin entrelazar)")
        elif typ == b"IDAT":
            idat.append(chunk)
        elif typ == b"IEND":
            break
        pos += 12 + ln
    bpp = {6: 4, 4: 2, 2: 3, 0: 1}[ctype]
    raw = zlib.decompress(b"".join(idat))
    stride = w * bpp
    prev = bytearray(stride)
    alpha = bytearray(w * h)
    i = 0
    for row in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if ft == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif ft == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif ft == 3:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif ft == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        if ctype in (6, 4):
            alpha[row * w:(row + 1) * w] = line[bpp - 1::bpp]
        else:
            alpha[row * w:(row + 1) * w] = b"\xff" * w
        prev = line
    return w, h, alpha


def walk_mask(path=IMAGE_PNG, threshold=100, dilate=2):
    w, h, a = read_png_alpha(path)
    m = bytearray(1 if v > threshold else 0 for v in a)
    for _ in range(dilate):
        n = bytearray(m)
        for y in range(h):
            base = y * w
            for x in range(w):
                if m[base + x]:
                    continue
                if (x > 0 and m[base + x - 1]) or (x < w - 1 and m[base + x + 1]) or (y > 0 and m[base - w + x]) or (y < h - 1 and m[base + w + x]):
                    n[base + x] = 1
        m = n
    return w, h, m


# ------------------------------------------------------------ calibración
def score(cal, pts, w, h, mask, cell=16):
    """precisión (puntos en zona caminable) × cobertura (celdas caminables con algún punto)."""
    inside = 0
    hit = set()
    sx, sy = cal["x_max"] - cal["x_min"], cal["y_max"] - cal["y_min"]
    for x, y in pts:
        u = (x - cal["x_min"]) / sx
        v = (y - cal["y_min"]) / sy
        if cal.get("invert_x"):
            u = 1 - u
        if cal.get("invert_y", True):
            v = 1 - v
        px, py = int(u * w), int(v * h)
        if 0 <= px < w and 0 <= py < h and mask[py * w + px]:
            inside += 1
            hit.add((px // cell, py // cell))
    return inside / max(len(pts), 1), len(hit)


def mask_cells(w, h, mask, cell=16):
    cells = set()
    for y in range(h):
        for x in range(w):
            if mask[y * w + x]:
                cells.add((x // cell, y // cell))
    return len(cells)


def fit(pts, image=IMAGE_PNG, log=print):
    """Busca span, centro e inversiones que maximizan precisión × cobertura."""
    w, h, mask = walk_mask(image)
    total_cells = mask_cells(w, h, mask)
    sample = pts[:: max(1, len(pts) // 3000)]

    def make(span, cx, cy, ix, iy):
        return {"x_min": cx - span / 2, "x_max": cx + span / 2, "y_min": cy - span / 2, "y_max": cy + span / 2, "invert_x": ix, "invert_y": iy}

    def evaluate(c, p=sample):
        prec, hit = score(c, p, w, h, mask)
        return prec * (hit / total_cells), prec, hit / total_cells

    best = None
    for ix in (False, True):
        for iy in (False, True):
            for span in range(20500, 23001, 250):
                for cx in range(-450, 451, 150):
                    for cy in range(-450, 451, 150):
                        c = make(span, cx, cy, ix, iy)
                        s = evaluate(c)
                        if best is None or s[0] > best[0][0]:
                            best = (s, span, cx, cy, ix, iy)
    log(f"[calibración] búsqueda gruesa: {best}")
    (_, span, cx, cy, ix, iy) = best
    for stepsz in (50, 20):
        improved = True
        while improved:
            improved = False
            for ds, dx, dy in [(stepsz, 0, 0), (-stepsz, 0, 0), (0, stepsz, 0), (0, -stepsz, 0), (0, 0, stepsz), (0, 0, -stepsz)]:
                c = make(span + ds, cx + dx, cy + dy, ix, iy)
                s = evaluate(c)
                if s[0] > best[0][0]:
                    best = (s, span + ds, cx + dx, cy + dy, ix, iy)
                    span, cx, cy = span + ds, cx + dx, cy + dy
                    improved = True
    final = make(span, cx, cy, ix, iy)
    full = evaluate(final, pts)
    alt = evaluate(make(span, -cx, -cy, not ix, not iy), pts)  # el mapa es casi simétrico al girarlo 180°
    final.update({"source": "ajuste por máscara", "score": round(full[0], 4), "precision": round(full[1], 4),
                  "coverage": round(full[2], 4), "rotated_alternative_score": round(alt[0], 4), "n_points": len(pts)})
    return final


def compare(cals, pts, image=IMAGE_PNG):
    w, h, mask = walk_mask(image)
    total = mask_cells(w, h, mask)
    out = {}
    for name, c in cals.items():
        prec, hit = score(c, pts, w, h, mask)
        out[name] = {"precision": round(prec, 4), "coverage": round(hit / total, 4), "score": round(prec * hit / total, 4)}
    return out


def alive_points(match_datas, step=5):
    from .matches import decode_positions
    pts = []
    for d in match_datas:
        pos = decode_positions(d["match_info"], step=step)
        for p in pos["players"]:
            pts += [(x, y) for x, y in zip(p["x"], p["y"]) if x is not None]
    return pts
