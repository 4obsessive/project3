"""KOTH / Rifts: cash-ins del demo de cada partida, quién los completa y si estaba en remontada."""
from .. import metric
from .m04_midboss import REGLA, _remontada


@metric("koth", "KOTH / Rifts", order=50)
def koth(ctx):
    k = ctx.demo_n
    cov = ctx.demo_coverage()
    title = "Eventos KOTH / Rifts (demo)"
    if not k:
        return [cov, {"type": "unavailable", "title": title,
                      "reason": "La API de partidas no trae los KOTH y ninguna partida analizada tiene datos del demo."}]
    rows = []
    for m in ctx.matches:
        d = m.demo
        if not d:
            continue
        for e in d.get("koth") or []:
            by = e.get("completed_by")
            rows.append({
                "match_id": m.id, "n": e.get("n"), "start_t": e.get("start_t"), "completed_t": e.get("completed_t"),
                "completa": {"us": "Este equipo", "them": "Rival"}.get(m.rel(by), "No completado"),
                "remontada": _remontada(m.mi, e.get("start_t"), by),
            })
    if not rows:
        return [cov, {"type": "unavailable", "title": title, "reason": "Los demos analizados no registran ningún KOTH."}]
    us = [r for r in rows if r["completa"] == "Este equipo"]
    them = [r for r in rows if r["completa"] == "Rival"]
    none = [r for r in rows if r["completa"] == "No completado"]
    return [cov,
            {"type": "text", "tone": "info",
             "text": f"Remontada: el equipo que completa el KOTH tenía {REGLA} al empezar el cash-in; «—» si no hay muestras de net worth."},
            {"type": "text", "tone": "confirmed",
             "text": f"{len(rows)} KOTH en {k} partidas con demo: completados por este equipo {len(us)} "
                     f"({sum(1 for r in us if r['remontada'] == 'sí')} en remontada), por el rival {len(them)} "
                     f"({sum(1 for r in them if r['remontada'] == 'sí')} en remontada), sin completar {len(none)}."},
            {"type": "table", "title": "KOTH: quién completa el cash-in", "n": k,
             "columns": [{"key": "match_id", "label": "Partida"}, {"key": "n", "label": "#"},
                         {"key": "start_t", "label": "Inicio", "fmt": "mmss"}, {"key": "completed_t", "label": "Completado", "fmt": "mmss"},
                         {"key": "completa", "label": "Lo completa"}, {"key": "remontada", "label": "En remontada"}],
             "rows": rows}]
