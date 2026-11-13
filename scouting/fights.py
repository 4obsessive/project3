"""Clasifica cada muerte (= kill del rival) de una partida: pelea de midboss, de KOTH, resto o desconocida.

Reglas (posición = donde murió la víctima):
- Midboss: a <= MIDBOSS_RADIUS de PIT y tiempo en [primer daño al midboss, su muerte + AFTER_S].
  Sin demo (o midboss sin t_first, solo rejuvenators): [muerte - AFTER_S, muerte + AFTER_S], con la
  muerte de metadata `mid_boss[].destroyed_time_s`. Una ventana por midboss.
- KOTH: a <= RIFT_RADIUS de alguno de RIFTS y tiempo en [inicio del cash-in, fin + AFTER_S].
  Solo con demo ("done"); sin demo `koth_known` es False y nada se marca koth.
  Regla fija: si `end_t` es None, la ventana es [start_t, start_t + KOTH_OPEN_S + AFTER_S] (120 s:
  plazo típico del cash-in + 60 s después).
- Si caen en ambas ventanas, gana el objetivo más cercano.
- Sin posición -> "unknown" (cuenta en totales, no en mapas ni en resto/objetivo).
"""
import math

from . import matches

MIDBOSS_RADIUS = 2500
RIFT_RADIUS = 2000
AFTER_S = 60
KOTH_OPEN_S = 60
RIFTS = [(-7648, 0), (7648, 0)]
PIT = (0, 0)


def _midboss_windows(mi, demo_summary):
    if demo_summary and demo_summary.get("state") == "done":
        out = []
        for m in demo_summary.get("midboss") or []:
            if m.get("t") is None:
                continue
            ini = m["t_first"] if m.get("t_first") is not None else m["t"] - AFTER_S
            out.append((ini, m["t"] + AFTER_S))
        return out
    return [(m["destroyed_time_s"] - AFTER_S, m["destroyed_time_s"] + AFTER_S)
            for m in mi.get("mid_boss") or [] if m.get("destroyed_time_s") is not None]


def _koth_windows(demo_summary):
    out = []
    for k in demo_summary.get("koth") or []:
        if k.get("start_t") is None:
            continue
        fin = k["end_t"] + AFTER_S if k.get("end_t") is not None else k["start_t"] + KOTH_OPEN_S + AFTER_S
        out.append((k["start_t"], fin))
    return out


def _in(t, windows):
    return any(a <= t <= b for a, b in windows)


def _nearest_objective(x, y):
    """'midboss' o 'koth' según el objetivo más cercano (empate -> midboss)."""
    d_pit = math.hypot(x - PIT[0], y - PIT[1])
    d_rift = min(math.hypot(x - rx, y - ry) for rx, ry in RIFTS)
    return "midboss" if d_pit <= d_rift else "koth"


def counts(result):
    """{"midboss", "koth", "rest", "unknown"} -> nº de muertes de cada tipo en un resultado de `classify`."""
    out = {"midboss": 0, "koth": 0, "rest": 0, "unknown": 0}
    for e in result["events"]:
        out[e["fight"]] += 1
    return out


def classify(mi, demo_summary=None):
    """-> {"koth_known": bool, "events": [{**death_event, "fight": ...}]}"""
    koth_known = bool(demo_summary) and demo_summary.get("state") == "done"
    mb_w = _midboss_windows(mi, demo_summary)
    k_w = _koth_windows(demo_summary) if koth_known else []
    events = []
    for e in matches.deaths(mi):
        x, y, t = e.get("x"), e.get("y"), e.get("t")
        if x is None or y is None or t is None:
            fight = "unknown"
        else:
            es_mb = _in(t, mb_w) and math.hypot(x - PIT[0], y - PIT[1]) <= MIDBOSS_RADIUS
            es_k = _in(t, k_w) and min(math.hypot(x - rx, y - ry) for rx, ry in RIFTS) <= RIFT_RADIUS
            if es_mb and es_k:
                fight = _nearest_objective(x, y)
            else:
                fight = "midboss" if es_mb else "koth" if es_k else "rest"
        events.append({**e, "fight": fight})
    return {"koth_known": koth_known, "events": events}
