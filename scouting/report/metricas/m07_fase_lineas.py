"""Fase de líneas (min 0–10): dúos por línea, daño, Guardians y primer gankeo. Los números salen de cada partida
(lanephase.lane_phase), igual que en la vista de partida; el daño solo promedia partidas con demo."""
from collections import Counter, defaultdict

from .. import metric
from ... import matches as M


def _mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def _min(t):
    return None if t is None else round(t / 60, 1)


def _int(x):
    return None if x is None else int(round(x))


def _no_cae(vals, n):
    k = sum(1 for v in vals if v is None)
    return f"{k} de {n}"


def _top(counter, ctx, limit=3):
    return ", ".join(f"{ctx.hero(h)} ({k})" for h, k in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]) or None


@metric("fase_lineas", "Fase de líneas (min 0–10)", order=70)
def fase_lineas(ctx):
    names = {int(k): v["nombre"] for k, v in M.lanes_payload().items()}
    ln = lambda l: names.get(l, f"Carril {l}")
    duo = defaultdict(list)       # (carril, héroes ordenados) -> [(entrada propia, demo?)]
    lane_m = defaultdict(list)    # carril -> [(propia, rival, slot->hero, demo?)]
    valid = demo_n = 0
    for m in ctx.matches:
        lp = m.lane_phase
        if not lp["valid"]:
            continue
        valid += 1
        is_demo = lp["source"] == "demo"
        demo_n += is_demo
        hero_of = {s: p.get("hero_id") for s, p in M.players(m.mi).items()}
        for lane_s, per in lp["lanes"].items():
            mine, theirs = per.get(str(m.our)), per.get(str(m.their))
            if not mine:
                continue
            duo[(int(lane_s), tuple(sorted(h for h in mine["heroes"] if h is not None)))].append((mine, is_demo))
            lane_m[int(lane_s)].append((mine, theirs, hero_of, is_demo))
    cov = {"type": "text", "tone": "confirmed" if valid == ctx.n and demo_n == ctx.n else "warning",
           "text": f"Partidas con líneas válidas (dos contra dos): {valid} de {ctx.n}. Con demo de fase de líneas: {demo_n} de {ctx.n}. "
                   "El daño solo promedia las partidas con demo; el resto se excluye, no se estima."}
    if not valid:
        return [cov, {"type": "unavailable", "title": "Fase de líneas", "reason": "Ninguna partida tiene líneas válidas (dos jugadores por línea y equipo)."}]
    blocks = [ctx.sample_warning(valid), cov]
    if not demo_n:
        blocks.append({"type": "unavailable", "title": "Daño en fase de líneas",
                       "reason": "Sin demo de fase de líneas no hay desglose de daño por línea: no disponible."})
    for lane in sorted({k[0] for k in duo}):
        rows = []
        for (l, heroes), items in duo.items():
            if l != lane:
                continue
            es = [e for e, _ in items]
            dm = [e for e, d in items if d]
            n = len(es)
            gt = [e["guardian_taken_t"] for e in es]
            gl = [e["guardian_lost_t"] for e in es]
            rows.append({"carril_id": lane, "duo": " + ".join(ctx.hero(h) for h in heroes) or "–", "n": n, "n_demo": len(dm),
                         "dmg_done": _int(_mean([e["dmg_done"] for e in dm])), "dmg_taken": _int(_mean([e["dmg_taken"] for e in dm])),
                         "dmg_taken_gank": _int(_mean([e["dmg_taken_gank"] for e in dm])),
                         "g_taken": _min(_mean(gt)), "g_taken_no": _no_cae(gt, n),
                         "g_lost": _min(_mean(gl)), "g_lost_no": _no_cae(gl, n)})
        rows.sort(key=lambda r: (r["dmg_done"] is None, -(r["dmg_done"] or 0), -r["n"]))
        blocks.append({"type": "table", "kind": "duos", "title": f"Dúos propios en {ln(lane)}", "n": len(lane_m[lane]),
                       "note": "Dúo = pareja de héroes sin orden. Daño medio por dúo en los 10 primeros minutos (solo partidas con demo). "
                               "Guardian: minuto medio de la caída; el que no cae no entra en la media.",
                       "columns": [{"key": "carril_id", "label": "Línea", "fmt": "lane"}, {"key": "duo", "label": "Dúo"},
                                   {"key": "n", "label": "Partidas"}, {"key": "n_demo", "label": "Con demo"},
                                   {"key": "dmg_done", "label": "Daño hecho"}, {"key": "dmg_taken", "label": "Daño recibido"},
                                   {"key": "dmg_taken_gank", "label": "Recibido de gankeos"},
                                   {"key": "g_taken", "label": "Guardian rival cae (min)"}, {"key": "g_taken_no", "label": "Rival no cae en"},
                                   {"key": "g_lost", "label": "Guardian propio cae (min)"}, {"key": "g_lost_no", "label": "Propio no cae en"}],
                       "rows": rows})
    # primer gankeo por línea
    grows = []
    for lane in sorted(lane_m):
        suf, mad, suf_h, mad_h = [], [], Counter(), Counter()
        for mine, theirs, hero_of, _ in lane_m[lane]:
            s, g = mine.get("first_gank_suffered"), mine.get("first_gank_made")
            if s:
                suf.append(s["t"])
                suf_h[hero_of.get(s["attacker_slot"])] += 1
            if g:
                mad.append(g["t"])
                mad_h[hero_of.get(g["attacker_slot"])] += 1
        N = len(lane_m[lane])
        grows.append({"carril_id": lane, "n": N, "suf_n": len(suf), "suf_mean": _min(_mean(suf)), "suf_min": _min(min(suf)) if suf else None,
                      "suf_heroes": _top(suf_h, ctx), "made_n": len(mad), "made_mean": _min(_mean(mad)),
                      "made_min": _min(min(mad)) if mad else None, "made_heroes": _top(mad_h, ctx)})
        if N >= 3 and len(suf) / N >= 0.5:
            ctx.finding("weakness", f"Sufren un gankeo en {ln(lane)} (primero, tras el min 1) en {len(suf)} de {N} partidas.", len(suf), N)
        if N >= 3 and len(mad) / N >= 0.5:
            ctx.finding("strength", f"Gankean en {ln(lane)} (primero, tras el min 1) en {len(mad)} de {N} partidas.", len(mad), N)
    blocks.append({"type": "table", "kind": "ganks", "title": "Primer gankeo por línea", "n": valid,
                   "note": "Gankeo = daño o kill sobre un jugador de otra línea tras el min 1. Minutos medio y mínimo de las partidas en que ocurre; "
                           "los héroes son los que lo hacen más veces.",
                   "columns": [{"key": "carril_id", "label": "Línea", "fmt": "lane"}, {"key": "n", "label": "Partidas"},
                               {"key": "suf_n", "label": "Lo sufren (partidas)"}, {"key": "suf_mean", "label": "Min medio"}, {"key": "suf_min", "label": "Min mínimo"},
                               {"key": "suf_heroes", "label": "Rivales que más gankean"},
                               {"key": "made_n", "label": "Lo hacen (partidas)"}, {"key": "made_mean", "label": "Min medio"}, {"key": "made_min", "label": "Min mínimo"},
                               {"key": "made_heroes", "label": "Propios que más gankean"}],
                   "rows": grows})
    return blocks
