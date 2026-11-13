"""Score v2: componentes por percentil, ajustados por héroe y encogidos según la muestra.

Cada componente es un percentil 0–1 frente a los jugadores con >= MIN_N partidas:
  win  = winrate ajustado (Beta prior de la población)
  kda  = índice KDA relativo a la media de jugadores seguidos en los mismos héroes
  dmg  = índice de daño/min, econ = índice de oro/min, obj = índice de daño a objetivos/min
  pool = nº efectivo de héroes (1/Σ cuota²) con >= 5 partidas
El cliente solo aplica pesos (static/js/score.js)."""
from . import stats

MIN_N = 20
DEFAULT_WEIGHTS = {"win": 30, "kda": 25, "dmg": 15, "econ": 15, "obj": 5, "pool": 10}
METRICS = ("kda", "dmg", "nw", "obj")
POOL_MIN = 5


def hero_metrics(h):
    """Métricas por héroe a partir de los acumulados (claves m, k, d, a, dmg, t, nwm, objm)."""
    mins = h["t"] / 60.0
    return {
        "kda": (h["k"] + h["a"]) / max(h["d"], 1),
        "dmg": h["dmg"] / mins if mins else None,
        "nw": h["nwm"] / mins if mins else None,
        "obj": h["objm"] / mins if mins else None,
    }


def baselines(per_player_heroes, population=None, min_pool=100):
    """{hero_id: {kda, dmg, nw, obj}} agrupando a todos los jugadores seguidos.

    Si un héroe tiene < min_pool partidas en total y hay base de la población (`population`,
    {hero_id: {kda: ...}}), se usan los valores de la población que existan."""
    pooled = {}
    for heroes in per_player_heroes:
        for hid, h in heroes.items():
            p = pooled.setdefault(hid, {"m": 0, "k": 0, "d": 0, "a": 0, "dmg": 0, "t": 0, "nwm": 0.0, "objm": 0.0})
            for key in p:
                p[key] += h.get(key, 0) or 0
    out = {}
    for hid, p in pooled.items():
        if p["m"] <= 0:
            continue
        b = hero_metrics(p)
        if p["m"] < min_pool and population and hid in population:
            b.update({k: v for k, v in population[hid].items() if v})
        out[hid] = b
    return out


def player_indices(heroes, base):
    """Índices ponderados por partidas: Σ n_h·(x_ph/base_h) / Σ n_h (1.0 = media en esos héroes)."""
    out = {}
    for metric in METRICS:
        num = den = 0.0
        for hid, h in heroes.items():
            if h["m"] <= 0:
                continue
            x = hero_metrics(h)[metric]
            b = (base.get(hid) or {}).get(metric)
            if x is None or not b:
                continue
            num += h["m"] * (x / b)
            den += h["m"]
        out[metric] = num / den if den else None
    return out


def effective_pool(heroes, min_matches=POOL_MIN):
    ms = [h["m"] for h in heroes.values() if h["m"] >= min_matches]
    tot = sum(ms)
    if not tot:
        return 1.0 if any(h["m"] > 0 for h in heroes.values()) else None
    return 1.0 / sum((m / tot) ** 2 for m in ms)


def score_from_parts(parts, weights=None):
    w = weights or DEFAULT_WEIGHTS
    tot = sum(max(0, w.get(k, 0)) for k in DEFAULT_WEIGHTS)
    if not tot or not parts:
        return None
    s = 0.0
    for k in DEFAULT_WEIGHTS:
        v = parts.get(k)
        s += max(0, w.get(k, 0)) * (v if v is not None else 0.5)
    return 100.0 * s / tot


def score_all(rows):
    """rows: lista de dicts con n, wr_adj, wr_lo, wr_hi, idx (dict de METRICS) y pool.

    Añade a cada fila: idx_adj, score_parts, score_default, score_lo, score_hi, provisional."""
    for r in rows:
        r["idx_adj"] = {m: (stats.shrink_ratio(r["idx"].get(m), r["n"], 1.0, 15) if r["n"] else None) for m in METRICS}
    ref = [r for r in rows if r["n"] >= MIN_N] or [r for r in rows if r["n"] > 0]
    pct = {
        "win": stats.percentile_fn([r["wr_adj"] for r in ref]),
        "kda": stats.percentile_fn([r["idx_adj"]["kda"] for r in ref]),
        "dmg": stats.percentile_fn([r["idx_adj"]["dmg"] for r in ref]),
        "econ": stats.percentile_fn([r["idx_adj"]["nw"] for r in ref]),
        "obj": stats.percentile_fn([r["idx_adj"]["obj"] for r in ref]),
        "pool": stats.percentile_fn([r["pool"] for r in ref]),
    }
    for r in rows:
        if not r["n"]:
            r.update(score_parts=None, score_default=None, score_lo=None, score_hi=None, provisional=True)
            continue
        parts = {
            "win": pct["win"](r["wr_adj"]), "kda": pct["kda"](r["idx_adj"]["kda"]),
            "dmg": pct["dmg"](r["idx_adj"]["dmg"]), "econ": pct["econ"](r["idx_adj"]["nw"]),
            "obj": pct["obj"](r["idx_adj"]["obj"]), "pool": pct["pool"](r["pool"]),
        }
        parts = {k: (round(v, 4) if v is not None else None) for k, v in parts.items()}
        r["score_parts"] = parts
        r["score_default"] = score_from_parts(parts)
        lo, hi = dict(parts), dict(parts)
        lo["win"] = pct["win"](r["wr_lo"])
        hi["win"] = pct["win"](r["wr_hi"])
        r["score_lo"], r["score_hi"] = score_from_parts(lo), score_from_parts(hi)
        r["parts_lo_win"], r["parts_hi_win"] = lo["win"], hi["win"]
        r["provisional"] = r["n"] < MIN_N
    return rows
