"""KOTH / Rifts: no disponible en los datos. Solo la pista «Comeback Gold Koth»."""
from .. import metric
from ... import matches as M


@metric("koth", "KOTH / Rifts", order=50)
def koth(ctx):
    rows = []
    us_n = them_n = 0
    for m in ctx.matches:
        sid = M.custom_stat_id(m.mi, "Comeback Gold Koth")
        if sid is None:
            continue
        vals = {0: 0, 1: 0}
        for p in m.mi.get("players") or []:
            v = M.final_custom_stat(p, sid) or 0
            vals[p.get("team")] = vals.get(p.get("team"), 0) + v
        us, them = vals.get(m.our, 0), vals.get(m.their, 0)
        us_n += us > 0
        them_n += them > 0
        rows.append({"match_id": m.id, "us": us, "them": them, "resultado": "Victoria" if m.won else "Derrota"})
    return [
        {"type": "unavailable", "title": "Eventos KOTH / Rifts",
         "reason": "La API no trae eventos de KOTH ni de Rifts: ni ganador, ni tiempos, ni recuento."},
        {"type": "text", "tone": "interpretation",
         "text": "Única pista: la estadística «Comeback Gold Koth» (oro de remontada obtenido en KOTH). Un valor > 0 indica que el equipo "
                 "ganó al menos un KOTH yendo por detrás. No es un recuento de KOTH ganados."},
        {"type": "text", "tone": "confirmed",
         "text": f"Con oro de remontada KOTH > 0: este equipo en {us_n} de {len(rows)} partidas; el rival en {them_n}."},
        {"type": "table", "title": "Comeback Gold Koth por partida (suma del equipo)", "n": len(rows),
         "columns": [{"key": "match_id", "label": "Partida"}, {"key": "us", "label": "Este equipo"}, {"key": "them", "label": "Rival"}, {"key": "resultado", "label": "Resultado"}],
         "rows": rows},
    ]
