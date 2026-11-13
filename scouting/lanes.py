"""Línea de cada jugador en la fase de líneas, deducida de sus posiciones (no de assigned_lane)."""
import json
import math
import os
import statistics

from . import matches

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATHS_FILE = os.path.join(ROOT, "lane_paths.json")

# Ventana de la fase de líneas (segundos de partida) sobre la que se miden las posiciones.
T_INI, T_FIN = 60, 300
LANES = (1, 3, 4)


def load_paths(path=None):
    """Recorridos de cada carril [{"lane", "points"}] desde lane_paths.json."""
    with open(path or PATHS_FILE, encoding="utf-8") as f:
        return json.load(f).get("paths") or []


def _mediana(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _lane_of(x, y, paths):
    """Carril cuyo recorrido pasa más cerca del punto (x, y)."""
    best, best_d = None, None
    for p in paths:
        for px, py in p["points"]:
            d = (px - x) ** 2 + (py - y) ** 2
            if best_d is None or d < best_d:
                best, best_d = p["lane"], d
    return best


def assign_lanes(mi, paths):
    """{slot: línea}. Mediana de la posición viva en T_INI..T_FIN → recorrido más cercano.

    Si algún jugador no tiene posiciones vivas o no hay exactamente 2 por equipo y línea,
    todas las líneas son None (la deducción no es fiable)."""
    dec = matches.decode_positions(mi)
    # Índice de muestra = segundo / interval_s (no siempre 1 s por muestra); ventana T_INI..T_FIN en segundos.
    iv = dec.get("interval_s") or 1
    i0, i1 = int(math.ceil(T_INI / iv)), int(T_FIN // iv)
    raw = {}
    for p in dec["players"]:
        mx = _mediana(p["x"][i0:i1])
        my = _mediana(p["y"][i0:i1])
        raw[p["slot"]] = (p["team"], None if mx is None or my is None else _lane_of(mx, my, paths))
    for p in mi.get("players") or []:
        raw.setdefault(p["player_slot"], (p.get("team"), None))
    out = {slot: lane for slot, (_, lane) in raw.items()}
    teams = {t for t, _ in raw.values()}
    ok = bool(raw) and all(
        sum(1 for t, l in raw.values() if t == team and l == lane) == 2
        for team in teams for lane in LANES)
    return out if ok else {slot: None for slot in raw}


def duos(mi, lanes):
    """{equipo: {línea: [slot, slot]}}; vacío si las líneas no son válidas."""
    if not lanes or any(v is None for v in lanes.values()):
        return {}
    ps = matches.players(mi)
    res = {}
    for slot, lane in sorted(lanes.items()):
        res.setdefault(ps[slot]["team"], {}).setdefault(lane, []).append(slot)
    return res
