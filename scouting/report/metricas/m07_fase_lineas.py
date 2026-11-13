"""Fase de líneas (min 0–10): dúos por línea, daño, Guardians y primer gankeo. Los números salen de cada partida
(lanephase.lane_phase), igual que en la vista de partida; el daño y el primer gankeo solo usan partidas con demo."""
from collections import Counter, defaultdict

from .. import metric
from ... import matches as M


def _mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def _sec(t):
    return None if t is None else int(round(t))


def _int(x):
    return None if x is None else int(round(x))


def _no_cae(vals, n):
    k = sum(1 for v in vals if v is None)
    return f"{k} of {n}"


def _ranked(counter, limit=3):
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0] is None, kv[0] or 0))[:limit]


def _top(counter, ctx, limit=3):
    return ", ".join(f"{ctx.hero(h)} ({k})" for h, k in _ranked(counter, limit)) or None


def _top_ids(counter, limit=3):
    return [h for h, _ in _ranked(counter, limit) if h is not None]


def _tied_max(rows, key):
    """Filas con el valor máximo de `key` (todas si hay empate); [] si no hay valores > 0."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    best = max(vals) if vals else None
    if not best or best <= 0:
        return []
    return [r for r in rows if r.get(key) == best]


@metric("fase_lineas", "Laning phase (min 0–10)", order=70)
def fase_lineas(ctx):
    names = {int(k): v["nombre"] for k, v in M.lanes_payload().items()}
    ln = lambda l: names.get(l, f"Lane {l}")
    duo = defaultdict(list)       # (carril, héroes ordenados) -> [(entrada propia, demo?)]
    lane_m = defaultdict(list)    # carril -> [(propia, rival, slot->hero, demo?)]
    valid = demo_n = incompleto = 0
    for m in ctx.matches:
        lp = m.lane_phase
        if not lp["valid"]:
            continue
        incompleto += bool(lp.get("demo_incompleto"))
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
           "text": f"Matches with valid lanes (two vs two): {valid} of {ctx.n}. With laning-phase demo: {demo_n} of {ctx.n}. "
                   "Damage only averages the matches with demo; the rest are excluded, not estimated."
                   + (f" Incomplete demo (pauses leave part of the first 10 minutes out), counted as no demo: {incompleto} of {ctx.n}."
                      if incompleto else "")}
    if not valid:
        return [cov, {"type": "unavailable", "title": "Laning phase", "reason": "No match has valid lanes (two players per lane and team)."}]
    blocks = [ctx.sample_warning(valid), cov]
    if not demo_n:
        blocks.append({"type": "unavailable", "title": "Laning-phase damage",
                       "reason": "Without a laning-phase demo there is no damage breakdown per lane."})
    duo_cards = []
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
            rows.append({"carril_id": lane, "duo": " + ".join(ctx.hero(h) for h in heroes) or "–", "hero_ids": list(heroes),
                         "n": n, "n_demo": len(dm),
                         "dmg_done": _int(_mean([e["dmg_done"] for e in dm])), "dmg_taken": _int(_mean([e["dmg_taken"] for e in dm])),
                         "dmg_taken_gank": _int(_mean([e["dmg_taken_gank"] for e in dm])),
                         "g_taken": _sec(_mean(gt)), "g_taken_no": _no_cae(gt, n),
                         "g_lost": _sec(_mean(gl)), "g_lost_no": _no_cae(gl, n)})
        rows.sort(key=lambda r: (r["dmg_done"] is None, -(r["dmg_done"] or 0), -r["n"]))
        tied = _tied_max(rows, "dmg_done")
        for r in tied:
            duo_cards.append({"title": f"Top damage duo · {ln(lane)}" + (" (tie)" if len(tied) > 1 else ""), "value": r["dmg_done"], "fmt": "int", "unit": "damage dealt (mean)",
                              "sub": r["duo"], "hero_ids": r["hero_ids"], "lane": lane, "n": r["n_demo"]})
        blocks.append({"type": "table", "kind": "duos", "title": f"Own duos in {ln(lane)}", "n": len(lane_m[lane]),
                       "note": "Duo = pair of heroes, unordered. Mean damage per duo in the first 10 minutes (matches with demo only). "
                               "Guardian: mean time it falls over the whole match (not only the laning phase); one that does not fall is left out of the mean.",
                       "columns": [{"key": "carril_id", "label": "Lane", "fmt": "lane"}, {"key": "duo", "label": "Duo", "fmt": "heroes"},
                                   {"key": "n", "label": "Matches"}, {"key": "n_demo", "label": "With demo"},
                                   {"key": "dmg_done", "label": "Damage dealt", "fmt": "int", "bar": True}, {"key": "dmg_taken", "label": "Damage taken", "fmt": "int", "bar": True},
                                   {"key": "dmg_taken_gank", "label": "Taken from ganks", "fmt": "int", "bar": True},
                                   {"key": "g_taken", "label": "Enemy Guardian falls", "fmt": "mmss", "objective": "Guardian"},
                                   {"key": "g_taken_no", "label": "Enemy's does not fall in"},
                                   {"key": "g_lost", "label": "Own Guardian falls", "fmt": "mmss", "objective": "Guardian"},
                                   {"key": "g_lost_no", "label": "Own does not fall in"}],
                       "rows": rows})
    if duo_cards:
        blocks.insert(2, {"type": "cards", "kind": "duo_cards", "items": duo_cards})
    # primer gankeo por línea: los gankeos necesitan el demo, así que solo cuentan las partidas con demo
    if not demo_n:
        blocks.append({"type": "unavailable", "title": "First gank by lane",
                       "reason": "Ganks need the laning-phase demo and no match has it."})
        return blocks
    grows = []
    for lane in sorted(lane_m):
        suf, mad, suf_h, mad_h = [], [], Counter(), Counter()
        con_demo = [x for x in lane_m[lane] if x[3]]
        for mine, theirs, hero_of, _ in con_demo:
            s, g = mine.get("first_gank_suffered"), mine.get("first_gank_made")
            if s:
                suf.append(s["t"])
                suf_h[hero_of.get(s["attacker_slot"])] += 1
            if g:
                mad.append(g["t"])
                mad_h[hero_of.get(g["attacker_slot"])] += 1
        N = len(con_demo)
        grows.append({"carril_id": lane, "n": N, "suf_n": len(suf), "suf_mean": _sec(_mean(suf)), "suf_min": min(suf) if suf else None,
                      "suf_heroes": _top(suf_h, ctx), "suf_hero_ids": _top_ids(suf_h),
                      "made_n": len(mad), "made_mean": _sec(_mean(mad)),
                      "made_min": min(mad) if mad else None, "made_heroes": _top(mad_h, ctx), "made_hero_ids": _top_ids(mad_h)})
        if N >= 3 and len(suf) / N >= 0.5:
            ctx.finding("weakness", f"They suffer a gank in {ln(lane)} (first one, after min 1) in {len(suf)} of {N} matches.", len(suf), N)
        if N >= 3 and len(mad) / N >= 0.5:
            ctx.finding("strength", f"They gank in {ln(lane)} (first one, after min 1) in {len(mad)} of {N} matches.", len(mad), N)
    tied = _tied_max(grows, "suf_n")
    gank_cards = [{"title": "Lane with most first ganks suffered" + (" (tie)" if len(tied) > 1 else ""), "value": r["suf_n"], "unit": f"of {r['n']} matches",
                   "sub": f"Enemies who gank most: {r['suf_heroes']}" if r["suf_heroes"] else None,
                   "hero_ids": r["suf_hero_ids"], "lane": r["carril_id"], "n": r["n"]} for r in tied]
    if gank_cards:
        blocks.append({"type": "cards", "kind": "gank_cards", "items": gank_cards})
    blocks.append({"type": "table", "kind": "ganks", "title": "First gank by lane", "n": demo_n,
                   "note": f"Gank = damage or kill on a player from another lane after min 1. Counts only matches with demo ({demo_n} of {valid} with valid lanes): "
                           "without demo, ganks are not available. Mean and earliest time over the matches where it happens; "
                           "the heroes are the ones who do it most often.",
                   "columns": [{"key": "carril_id", "label": "Lane", "fmt": "lane"}, {"key": "n", "label": "Matches"},
                               {"key": "suf_n", "label": "Suffered (matches)", "bar": True}, {"key": "suf_mean", "label": "Mean time", "fmt": "mmss"},
                               {"key": "suf_min", "label": "Earliest time", "fmt": "mmss"},
                               {"key": "suf_heroes", "label": "Enemies who gank most", "fmt": "heroes", "ids": "suf_hero_ids"},
                               {"key": "made_n", "label": "Made (matches)", "bar": True}, {"key": "made_mean", "label": "Mean time", "fmt": "mmss"},
                               {"key": "made_min", "label": "Earliest time", "fmt": "mmss"},
                               {"key": "made_heroes", "label": "Own heroes who gank most", "fmt": "heroes", "ids": "made_hero_ids"}],
                   "rows": grows})
    return blocks
