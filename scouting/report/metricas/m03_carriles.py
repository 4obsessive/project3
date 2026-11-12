"""Guardians y Walkers: qué carril pierden y presionan primero, tiempos y orden de destrucción."""
from collections import Counter, defaultdict

from .. import metric, stats
from ...matches import load_objective_map

TYPES = ("Guardian", "Walker")


def _step(r):
    return (r["type"], r["lane"])


@metric("carriles", "Guardians y Walkers por carril", order=30)
def carriles(ctx):
    objs, lane_names = load_objective_map()
    lanes = sorted({o["carril"] for o in objs.values() if o.get("tipo") in TYPES and o.get("carril")})
    present = set()
    first_lost, first_taken = Counter(), Counter()
    first_lost_t, first_taken_t = [], []
    times = defaultdict(list)  # (rel, tipo, carril) -> minutos
    seq_lost, seq_taken = Counter(), Counter()
    timeline = []
    race = Counter()  # quién gana la "carrera" del primer Guardian en cada partida
    for m in ctx.matches:
        rows = [r for r in m.objectives if r["type"] in TYPES and r["lane"]]
        for r in rows:
            present.add(r["lane"])
        ours = sorted((r for r in rows if r["owner_team"] == m.our and r["destroyed_s"]), key=lambda r: r["destroyed_s"])
        theirs = sorted((r for r in rows if r["owner_team"] == m.their and r["destroyed_s"]), key=lambda r: r["destroyed_s"])
        g_ours = [r for r in ours if r["type"] == "Guardian"]
        g_theirs = [r for r in theirs if r["type"] == "Guardian"]
        if g_ours:
            first_lost[g_ours[0]["lane"]] += 1
            first_lost_t.append(g_ours[0]["destroyed_s"])
        if g_theirs:
            first_taken[g_theirs[0]["lane"]] += 1
            first_taken_t.append(g_theirs[0]["destroyed_s"])
        a = g_theirs[0]["destroyed_s"] if g_theirs else None
        b = g_ours[0]["destroyed_s"] if g_ours else None
        if a is not None and (b is None or a < b):
            race["us"] += 1
        elif b is not None:
            race["them"] += 1
        for r in ours:
            times[("lost", r["type"], r["lane"])].append(r["destroyed_s"])
        for r in theirs:
            times[("taken", r["type"], r["lane"])].append(r["destroyed_s"])
        seq_lost[tuple(_step(r) for r in ours)] += 1 if ours else 0
        seq_taken[tuple(_step(r) for r in theirs)] += 1 if theirs else 0
        ev = [{"t": r["destroyed_s"], "label": f"{r['label']} perdido", "side": "them", "kind": r["type"]} for r in m.objectives if r["owner_team"] == m.our and r["destroyed_s"]]
        ev += [{"t": r["destroyed_s"], "label": f"{r['label']} rival destruido", "side": "us", "kind": r["type"]} for r in m.objectives if r["owner_team"] == m.their and r["destroyed_s"]]
        timeline.append({"label": f"{m.id} ({'V' if m.won else 'D'})", "duration": m.duration, "events": sorted(ev, key=lambda e: e["t"])})
    lanes = [l for l in lanes if l in present] or lanes
    ln = lambda l: lane_names.get(l, f"Carril {l}")
    n = ctx.n
    blocks = [ctx.sample_warning(),
              {"type": "text", "tone": "info", "text": "Carriles por color: York (amarillo), Broadway (azul) y Greenwich (verde); son los mismos para ambos equipos. "
                                                         "El mapeo de team_objective_id es inferido y se puede corregir en Partidas › Mapeo de objetivos."}]
    blocks.append({"type": "bars", "title": "Primer Guardian: carril", "unit": "%", "n": n,
                   "labels": [ln(l) for l in lanes], "lane_ids": list(lanes),
                   "series": [{"name": "Pierden primero", "side": "them", "values": [round(100 * first_lost[l] / n) for l in lanes]},
                              {"name": "Presionan primero (destruyen el del rival)", "side": "us", "values": [round(100 * first_taken[l] / n) for l in lanes]}]})
    fl, ft = stats(first_lost_t), stats(first_taken_t)
    blocks.append({"type": "text", "tone": "confirmed",
                   "text": f"Carrera del primer Guardian: lo tumban antes que el rival en {race['us']} de {n} partidas; el rival antes en {race['them']}. "
                           + (f"Primer Guardian perdido: minuto medio {fl['mean'] / 60:.1f}, mediana {fl['median'] / 60:.1f} ({fl['n']} partidas). " if fl["n"] else "No pierden ningún Guardian en la muestra. ")
                   + (f"Primer Guardian rival destruido: media {ft['mean'] / 60:.1f}, mediana {ft['median'] / 60:.1f} ({ft['n']} partidas)." if ft["n"] else "No destruyen ningún Guardian rival en la muestra.")})
    rows = []
    for l in lanes:
        row = {"carril": ln(l), "carril_id": l}
        for rel, lab in (("lost", "perd"), ("taken", "dest")):
            for tp in TYPES:
                s = stats(times[(rel, tp, l)])
                row[f"{lab}_{tp}_n"] = f"{s['n']}/{n}"
                row[f"{lab}_{tp}_med"] = s["median"]
                row[f"{lab}_{tp}_avg"] = s["mean"]
        rows.append(row)
    cols = [{"key": "carril", "label": "Carril", "fmt": "lane"}]
    for lab, txt in (("perd", "perdido"), ("dest", "destruido al rival")):
        for tp in TYPES:
            cols += [{"key": f"{lab}_{tp}_n", "label": f"{tp} {txt} (partidas)"},
                     {"key": f"{lab}_{tp}_avg", "label": "media", "fmt": "mmss"},
                     {"key": f"{lab}_{tp}_med", "label": "mediana", "fmt": "mmss"}]
    blocks.append({"type": "table", "title": "Tiempos por carril", "n": n, "columns": cols, "rows": rows})
    blocks.append({"type": "histogram", "title": "Minuto del primer Guardian", "bin_s": 60, "n": n,
                   "series": [{"name": "Perdido", "side": "them", "values": first_lost_t}, {"name": "Destruido al rival", "side": "us", "values": first_taken_t}]})
    for title, seq in (("Orden habitual en que pierden Guardians/Walkers", seq_lost), ("Orden habitual en que destruyen Guardians/Walkers rivales", seq_taken)):
        rows = [{"orden": [{"tipo": tp, "carril": l} for tp, l in k], "partidas": v, "pct": round(100 * v / n)} for k, v in seq.most_common(6) if k]
        blocks.append({"type": "table", "title": title, "n": n,
                       "columns": [{"key": "orden", "label": "Secuencia", "fmt": "lane_seq"}, {"key": "partidas", "label": "Partidas"}, {"key": "pct", "label": "%"}], "rows": rows})
    blocks.append({"type": "timeline", "title": "Línea de tiempo por partida", "n": n, "rows": timeline})

    # patrones
    if n >= 3:
        lane, cnt = (first_lost.most_common(1) or [(None, 0)])[0]
        if lane and cnt / n >= 0.5:
            ctx.finding("weakness", f"Pierden primero el Guardian del {ln(lane)} en {cnt} de {n} partidas.", cnt, n)
            ctx.finding("improve", f"Reforzar el {ln(lane)} en la fase de carriles (es el primero que cae en {cnt}/{n}).", cnt, n, confirmed=False)
        lane, cnt = (first_taken.most_common(1) or [(None, 0)])[0]
        if lane and cnt / n >= 0.5:
            ctx.finding("pattern", f"Presionan primero el {ln(lane)}: es el primer Guardian rival que cae en {cnt} de {n} partidas.", cnt, n)
        for l in lanes:
            never = n - len(times[("taken", "Guardian", l)])
            if never / n >= 0.6 and len(lanes) > 1:
                ctx.finding("opportunity", f"Rara vez destruyen el Guardian rival del {ln(l)} (no cae en {never} de {n} partidas): posible carril descuidado en ataque.", never, n, confirmed=False)
        if race["us"] / n >= 0.6:
            ctx.finding("strength", f"Tumban el primer Guardian rival antes de perder el suyo en {race['us']} de {n} partidas.", race["us"], n)
        elif race["them"] / n >= 0.6:
            ctx.finding("weakness", f"Pierden su primer Guardian antes de tumbar uno rival en {race['them']} de {n} partidas.", race["them"], n)
    return blocks
