"""Economía: diferencia de net worth a minutos fijos y su relación con el resultado."""
from .. import metric, stats
from ... import matches as M

MARKS = [5, 10, 15, 20, 25, 30, 35]


@metric("economia", "Economía (net worth)", order=60)
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
              {"type": "text", "tone": "info", "text": "Net worth interpolado entre las muestras de la partida (cada pocos minutos). Diferencia = este equipo − rival."},
              {"type": "bars", "title": "Diferencia de net worth (mediana)", "unit": "", "n": ctx.n,
               "labels": [f"min {t}" for t in MARKS], "series": [{"name": "Mediana", "side": "us", "values": med, "signed": True}]},
              {"type": "table", "title": "Diferencia de net worth por minuto", "n": ctx.n,
               "columns": [{"key": "min", "label": "Minuto"}, {"key": "partidas", "label": "Partidas"}, {"key": "media", "label": "Media", "fmt": "signed0"},
                           {"key": "mediana", "label": "Mediana", "fmt": "signed0"}, {"key": "por_delante", "label": "Por delante"}],
               "rows": rows}]
    behind = [w for d, w in behind10 if d < 0]
    ahead = [w for d, w in behind10 if d > 0]
    if behind10:
        blocks.append({"type": "text", "tone": "confirmed",
                       "text": f"A los 10 min van por delante en {len(ahead)} de {len(behind10)} partidas (ganan {sum(ahead)} de esas) y por detrás en {len(behind)} (ganan {sum(behind)})."})
    n = len(behind10)
    if n >= 3:
        if len(ahead) / n >= 0.65:
            ctx.finding("strength", f"Fase de carriles fuerte: van por delante en net worth a los 10 min en {len(ahead)} de {n} partidas.", len(ahead), n)
        elif len(behind) / n >= 0.65:
            ctx.finding("weakness", f"Salen por detrás de la fase de carriles: por detrás en net worth a los 10 min en {len(behind)} de {n} partidas.", len(behind), n)
        if len(behind) >= 3 and sum(behind) / len(behind) >= 0.5:
            ctx.finding("strength", f"Remontan: ganan {sum(behind)} de {len(behind)} partidas en las que iban por detrás a los 10 min.", sum(behind), len(behind))
        if len(ahead) >= 3 and sum(ahead) / len(ahead) < 0.5:
            ctx.finding("improve", f"Pierden {len(ahead) - sum(ahead)} de {len(ahead)} partidas en las que iban por delante a los 10 min.", len(ahead) - sum(ahead), len(ahead))
    blocks.extend(_economia_ampliada(ctx))
    return blocks


PHASE_LABELS = ["0-10 min", "10-20 min", "20 min-final"]
RATE_KEYS = [("troopers_kills", "Troopers/min"), ("jungla_kills", "Jungla/min"),
             ("troopers_jungla_kills", "Troopers + jungla/min"), ("net_worth", "Net worth/min")]


def _mean(vals):
    return sum(vals) / len(vals) if vals else 0


def _economia_ampliada(ctx):
    """Almas por fuente y ritmos por minuto por fase, equipo vs rival (media por partida)."""
    ecos = [(m, M.economy(m.mi)) for m in ctx.matches if m.duration > 0]
    if not ecos:
        return []
    n = len(ecos)
    ids = [i for i in M.GOLD_SOURCES if any(e["teams"][str(m.our)]["sources"].get(i) or e["teams"][str(m.their)]["sources"].get(i) for m, e in ecos)]
    us = [round(_mean([e["teams"][str(m.our)]["sources"].get(i, 0) for m, e in ecos])) for i in ids]
    them = [round(_mean([e["teams"][str(m.their)]["sources"].get(i, 0) for m, e in ecos])) for i in ids]
    blocks = [{"type": "text", "tone": "info",
               "text": "Las barras de fuentes son almas ganadas por fuente (gold_sources, acumulado de la partida). Net worth/min es el cambio de net worth por minuto, "
                       "que puede diferir de lo ganado (p. ej. las muertes restan almas)."},
              {"type": "bars", "title": "Almas por fuente (media por partida, equipo)", "unit": "", "n": n,
               "labels": [M.GOLD_SOURCES[i] for i in ids],
               "series": [{"name": "Rival", "side": "them", "values": them}, {"name": "Este equipo", "side": "us", "values": us}]}]
    # solo cuentan las partidas que llegaron a cada fase
    per = [[(m, e) for m, e in ecos if m.duration > e["phases"][j][0]] for j in range(3)]
    cols = [{"key": "metrica", "label": "Ritmo (equipo entero)"}]
    for j, lab in enumerate(PHASE_LABELS):
        cols += [{"key": f"us{j}", "label": f"{lab} · equipo (n={len(per[j])})"}, {"key": f"them{j}", "label": f"{lab} · rival (n={len(per[j])})"}]
    rows = []
    for key, label in RATE_KEYS:
        row = {"metrica": label}
        for j in range(3):
            row[f"us{j}"] = round(_mean([e["teams"][str(m.our)]["per_phase"][j][key] for m, e in per[j]]), 1)
            row[f"them{j}"] = round(_mean([e["teams"][str(m.their)]["per_phase"][j][key] for m, e in per[j]]), 1)
        rows.append(row)
    blocks.append({"type": "table", "title": "Ritmos por minuto por fase (media por partida)", "n": n, "columns": cols, "rows": rows})
    return blocks
