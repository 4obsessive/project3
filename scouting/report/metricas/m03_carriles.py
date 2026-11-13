"""Guardians y Walkers: qué carril pierden y presionan primero, tiempos y orden de destrucción."""
from collections import Counter, defaultdict

from .. import metric, stats
from ...matches import load_objective_map

TYPES = ("Guardian", "Walker")


def _step(r):
    return (r["type"], r["lane"])


@metric("carriles", "Guardians and Walkers by lane", order=30)
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
        ev = [{"t": r["destroyed_s"], "label": f"{r['label']} lost", "side": "them", "kind": r["type"], "owner": r["owner_team"]} for r in m.objectives if r["owner_team"] == m.our and r["destroyed_s"]]
        ev += [{"t": r["destroyed_s"], "label": f"{r['label']} destroyed (enemy's)", "side": "us", "kind": r["type"], "owner": r["owner_team"]} for r in m.objectives if r["owner_team"] == m.their and r["destroyed_s"]]
        timeline.append({"label": f"{m.id} ({'W' if m.won else 'L'})", "duration": m.duration, "events": sorted(ev, key=lambda e: e["t"])})
    lanes = [l for l in lanes if l in present] or lanes
    ln = lambda l: lane_names.get(l, f"Lane {l}")
    n = ctx.n
    blocks = [ctx.sample_warning(),
              {"type": "text", "tone": "info", "text": "Lanes by colour: York (yellow), Broadway (blue) and Greenwich (green); they are the same for both teams. "
                                                         "The team_objective_id mapping is inferred and can be corrected in Matches › Objective mapping."}]
    blocks.append({"type": "bars", "title": "First Guardian: lane", "unit": "%", "n": n,
                   "labels": [ln(l) for l in lanes], "lane_ids": list(lanes),
                   "series": [{"name": "Lose first", "side": "them", "values": [round(100 * first_lost[l] / n) for l in lanes]},
                              {"name": "Push first (destroy the enemy's)", "side": "us", "values": [round(100 * first_taken[l] / n) for l in lanes]}]})
    fl, ft = stats(first_lost_t), stats(first_taken_t)
    blocks.append({"type": "text", "tone": "confirmed",
                   "text": f"First Guardian race: they take one down before the enemy does in {race['us']} of {n} matches; the enemy first in {race['them']}. "
                           + (f"First Guardian lost: mean minute {fl['mean'] / 60:.1f}, median {fl['median'] / 60:.1f} ({fl['n']} matches). " if fl["n"] else "They lose no Guardian in the sample. ")
                   + (f"First enemy Guardian destroyed: mean {ft['mean'] / 60:.1f}, median {ft['median'] / 60:.1f} ({ft['n']} matches)." if ft["n"] else "They destroy no enemy Guardian in the sample.")})
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
    cols = [{"key": "carril", "label": "Lane", "fmt": "lane"}]
    for lab, txt in (("perd", "lost"), ("dest", "destroyed (enemy's)")):
        for tp in TYPES:
            cols += [{"key": f"{lab}_{tp}_n", "label": f"{tp} {txt} (matches)", "objective": tp},
                     {"key": f"{lab}_{tp}_avg", "label": "mean", "fmt": "mmss"},
                     {"key": f"{lab}_{tp}_med", "label": "median", "fmt": "mmss"}]
    blocks.append({"type": "table", "title": "Times by lane", "n": n, "columns": cols, "rows": rows})
    blocks.append({"type": "histogram", "title": "Minute of the first Guardian", "bin_s": 60, "n": n,
                   "series": [{"name": "Lost", "side": "them", "values": first_lost_t}, {"name": "Destroyed (enemy's)", "side": "us", "values": first_taken_t}]})
    for title, seq in (("Usual order in which they lose Guardians/Walkers", seq_lost), ("Usual order in which they destroy enemy Guardians/Walkers", seq_taken)):
        rows = [{"orden": [{"tipo": tp, "carril": l} for tp, l in k], "partidas": v, "pct": round(100 * v / n)} for k, v in seq.most_common(6) if k]
        blocks.append({"type": "table", "title": title, "n": n,
                       "columns": [{"key": "orden", "label": "Sequence", "fmt": "lane_seq"}, {"key": "partidas", "label": "Matches"}, {"key": "pct", "label": "%", "bar": True}], "rows": rows})
    blocks.append({"type": "timeline", "title": "Timeline per match", "n": n, "rows": timeline})

    # patrones (con 3 carriles, «el primero en caer» tiene una tasa base de 1/3 por azar)
    base = 1 / max(len(lanes), 1)
    if n >= 3:
        lane, cnt = (first_lost.most_common(1) or [(None, 0)])[0]
        if lane and cnt / n >= 0.5:
            ctx.finding("weakness", f"They lose the {ln(lane)} Guardian first in {cnt} of {n} matches.", cnt, n, baseline=base)
        lane, cnt = (first_taken.most_common(1) or [(None, 0)])[0]
        if lane and cnt / n >= 0.5:
            ctx.finding("pattern", f"They push {ln(lane)} first: it is the first enemy Guardian to fall in {cnt} of {n} matches.", cnt, n, baseline=base)
        if race["us"] / n >= 0.6:
            ctx.finding("strength", f"They take down the first enemy Guardian before losing their own in {race['us']} of {n} matches.", race["us"], n)
        elif race["them"] / n >= 0.6:
            ctx.finding("weakness", f"They lose their first Guardian before taking down an enemy one in {race['them']} of {n} matches.", race["them"], n)
    return blocks
