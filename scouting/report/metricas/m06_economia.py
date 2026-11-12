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
            ctx.finding("improve", f"Cerrar partidas: pierden {len(ahead) - sum(ahead)} de {len(ahead)} partidas en las que iban por delante a los 10 min.", len(ahead) - sum(ahead), len(ahead))
    return blocks
