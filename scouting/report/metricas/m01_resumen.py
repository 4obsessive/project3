"""Resumen de la muestra: lado, resultado, duración y kills por partida."""
import time

from .. import metric, stats
from ... import matches as M
from ... import stats as S


@metric("resumen", "Resumen de la muestra", order=10)
def resumen(ctx):
    rows = []
    for m in ctx.matches:
        kills = {0: 0, 1: 0}
        for p in m.mi.get("players") or []:
            kills[p.get("team")] = kills.get(p.get("team"), 0) + (p.get("kills") or 0)
        rows.append({
            "match_id": m.id,
            "fecha": time.strftime("%Y-%m-%d", time.localtime(m.mi.get("start_time") or 0)),
            "lado": f"{M.TEAM_NAMES[m.our]} (equipo {m.our})",
            "deteccion": "manual" if m.side_source == "manual" else f"auto ({m.roster_counts[m.our]} de la plantilla)",
            "resultado": "Victoria" if m.won else "Derrota",
            "duracion": m.duration,
            "kills": kills.get(m.our, 0), "muertes": kills.get(m.their, 0),
        })
    wins = sum(1 for m in ctx.matches if m.won)
    by_side = {}
    for side in (0, 1):
        ms = [m for m in ctx.matches if m.our == side]
        by_side[side] = (len(ms), sum(1 for m in ms if m.won))
    dur = stats([m.duration for m in ctx.matches])
    blocks = [
        ctx.sample_warning(),
        {"type": "text", "tone": "confirmed",
         "text": f"{ctx.n} partidas analizadas · {wins} victorias ({wins / ctx.n:.0%}) · duración media {dur['mean'] / 60:.1f} min, mediana {dur['median'] / 60:.1f} min."},
    ]
    if ctx.skipped:
        blocks.append({"type": "text", "tone": "warning",
                       "text": f"{len(ctx.skipped)} partidas excluidas por no poder detectar el lado: " + ", ".join(str(s["match_id"]) for s in ctx.skipped)})
    blocks.append({
        "type": "bars", "title": "Winrate por lado", "unit": "%", "n": ctx.n,
        "labels": [f"{M.TEAM_NAMES[s]} ({by_side[s][0]} partidas)" for s in (0, 1)],
        "series": [{"name": "Winrate", "side": "us", "values": [round(100 * by_side[s][1] / by_side[s][0]) if by_side[s][0] else None for s in (0, 1)],
                    "ci": [[round(100 * x) for x in S.wilson(by_side[s][1], by_side[s][0], S.Z90)] if by_side[s][0] else None for s in (0, 1)]}],
    })
    blocks.append({
        "type": "table", "title": "Partidas", "n": ctx.n,
        "columns": [{"key": "match_id", "label": "Partida"}, {"key": "fecha", "label": "Fecha"}, {"key": "lado", "label": "Lado"},
                    {"key": "deteccion", "label": "Detección"}, {"key": "resultado", "label": "Resultado"},
                    {"key": "duracion", "label": "Duración", "fmt": "mmss"}, {"key": "kills", "label": "Kills"}, {"key": "muertes", "label": "Kills rival"}],
        "rows": rows,
    })
    for s in (0, 1):
        n, w = by_side[s]
        on, ow = by_side[1 - s]
        # solo si ambos lados tienen ≥5 partidas y los intervalos de Wilson al 80 % no se solapan
        if n >= 5 and on >= 5:
            a, b = S.wilson(w, n, S.Z80), S.wilson(ow, on, S.Z80)
            if a[0] > b[1]:
                ctx.finding("pattern", f"Rinden mejor como {M.TEAM_NAMES[s]}: {w}/{n} victorias frente a {ow}/{on} en el otro lado.", w, n,
                            baseline=ow / on)
    return blocks
