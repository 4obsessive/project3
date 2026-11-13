"""Economía: diferencia de net worth a minutos fijos y su relación con el resultado."""
from .. import metric, stats
from ... import matches as M

MARKS = [5, 10, 15, 20, 25, 30, 35]


@metric("economia", "Economy (net worth)", order=60)
def economia(ctx):
    rows, med = [], []
    behind10 = []
    for t in MARKS:
        vals = [M.team_networth_at(m.mi, m.our, t * 60) - M.team_networth_at(m.mi, m.their, t * 60) for m in ctx.matches if m.duration >= t * 60]
        s = stats(vals)
        ahead = sum(1 for v in vals if v > 0)
        rows.append({"min": t, "partidas": s["n"], "media": s["mean"], "mediana": s["median"], "por_delante": f"{ahead}/{s['n']}"})
        med.append(round(s["median"]) if s["median"] is not None else None)
    for m in ctx.matches:
        if m.duration >= 600:
            d = M.team_networth_at(m.mi, m.our, 600) - M.team_networth_at(m.mi, m.their, 600)
            behind10.append((d, m.won))
    blocks = [ctx.sample_warning(),
              {"type": "text", "tone": "info", "text": "Net worth interpolated between the match samples (every few minutes). Difference = this team − enemy."},
              {"type": "bars", "title": "Net worth difference (median)", "unit": "", "n": ctx.n,
               "labels": [f"min {t}" for t in MARKS], "series": [{"name": "Median", "side": "us", "values": med, "signed": True}]},
              {"type": "table", "title": "Net worth difference by minute", "n": ctx.n,
               "columns": [{"key": "min", "label": "Minute"}, {"key": "partidas", "label": "Matches"}, {"key": "media", "label": "Mean", "fmt": "signed0"},
                           {"key": "mediana", "label": "Median", "fmt": "signed0"}, {"key": "por_delante", "label": "Ahead"}],
               "rows": rows}]
    behind = [w for d, w in behind10 if d < 0]
    ahead = [w for d, w in behind10 if d > 0]
    if behind10:
        blocks.append({"type": "text", "tone": "confirmed",
                       "text": f"At 10 min they are ahead in {len(ahead)} of {len(behind10)} matches (winning {sum(ahead)} of those) and behind in {len(behind)} (winning {sum(behind)})."})
    n = len(behind10)
    if n >= 3:
        if len(ahead) / n >= 0.65:
            ctx.finding("strength", f"Strong laning phase: ahead in net worth at 10 min in {len(ahead)} of {n} matches.", len(ahead), n)
        elif len(behind) / n >= 0.65:
            ctx.finding("weakness", f"They leave the laning phase behind: behind in net worth at 10 min in {len(behind)} of {n} matches.", len(behind), n)
        if len(behind) >= 3 and sum(behind) / len(behind) >= 0.5:
            ctx.finding("strength", f"They come back: they win {sum(behind)} of {len(behind)} matches in which they were behind at 10 min.", sum(behind), len(behind))
        if len(ahead) >= 3 and sum(ahead) / len(ahead) < 0.5:
            ctx.finding("improve", f"They lose {len(ahead) - sum(ahead)} of {len(ahead)} matches in which they were ahead at 10 min.", len(ahead) - sum(ahead), len(ahead))
    blocks.extend(_economia_ampliada(ctx))
    return blocks


PHASE_LABELS = ["0-10 min", "10-20 min", "20 min-end"]
RATE_KEYS = [("troopers_kills", "Troopers/min"), ("jungla_kills", "Jungle/min"),
             ("troopers_jungla_kills", "Troopers + jungle/min"), ("net_worth", "Net worth/min")]


def _r(v, d=0):
    return None if v is None else (round(v) if d == 0 else round(v, d))


def _mean(vals):
    return sum(vals) / len(vals) if vals else None


def _economia_ampliada(ctx):
    """Almas por fuente y ritmos por minuto por fase, equipo vs rival (media por partida)."""
    ecos = [(m, M.economy(m.mi)) for m in ctx.matches if m.duration > 0]
    if not ecos:
        return []
    n = len(ecos)
    ids = [i for i in M.GOLD_SOURCES if any(e["teams"][str(m.our)]["sources"].get(i) or e["teams"][str(m.their)]["sources"].get(i) for m, e in ecos)]
    us = [_r(_mean([e["teams"][str(m.our)]["sources"].get(i, 0) for m, e in ecos]), 0) for i in ids]
    them = [_r(_mean([e["teams"][str(m.their)]["sources"].get(i, 0) for m, e in ecos]), 0) for i in ids]
    blocks = [{"type": "text", "tone": "info",
               "text": "The source bars are souls earned per source (gold_sources, match total). Net worth/min is the change in net worth per minute, "
                       "which can differ from what was earned (e.g. deaths take souls away)."},
              {"type": "bars", "title": "Souls by source (mean per match, team)", "unit": "", "n": n,
               "labels": [M.GOLD_SOURCES[i] for i in ids],
               "series": [{"name": "Enemy", "side": "them", "values": them}, {"name": "This team", "side": "us", "values": us}]}]
    # solo cuentan las partidas que llegaron a cada fase
    per = [[(m, e) for m, e in ecos if m.duration > e["phases"][j][0]] for j in range(3)]
    cols = [{"key": "metrica", "label": "Rate (whole team)"}]
    for j, lab in enumerate(PHASE_LABELS):
        cols += [{"key": f"us{j}", "label": f"{lab} · team (n={len(per[j])})", "fmt": "1"},
                 {"key": f"them{j}", "label": f"{lab} · enemy (n={len(per[j])})", "fmt": "1"}]
    rows = []
    for key, label in RATE_KEYS:
        row = {"metrica": label}
        for j in range(3):
            row[f"us{j}"] = _r(_mean([e["teams"][str(m.our)]["per_phase"][j][key] for m, e in per[j]]), 1)
            row[f"them{j}"] = _r(_mean([e["teams"][str(m.their)]["per_phase"][j][key] for m, e in per[j]]), 1)
        rows.append(row)
    blocks.append({"type": "table", "title": "Per-minute rates by phase (mean per match)", "n": n, "columns": cols, "rows": rows})
    return blocks
