"""KOTH / Rifts: cash-ins del demo de cada partida, quién los completa y si estaba en remontada."""
from .. import metric
from .m04_midboss import REGLA, _remontada


@metric("koth", "KOTH / Rifts", order=50)
def koth(ctx):
    k = ctx.demo_n
    cov = ctx.demo_coverage()
    title = "KOTH / Rifts events (demo)"
    if not k:
        return [cov, {"type": "unavailable", "title": title,
                      "reason": "The match API does not include KOTH and no analysed match has demo data."}]
    rows = []
    for m in ctx.matches:
        d = m.demo
        if not d:
            continue
        for e in d.get("koth") or []:
            by = e.get("completed_by")
            rows.append({
                "match_id": m.id, "n": e.get("n"), "start_t": e.get("start_t"), "completed_t": e.get("completed_t"),
                "completa": {"us": "This team", "them": "Enemy"}.get(m.rel(by), "Not completed"),
                "remontada": _remontada(m.mi, e.get("start_t"), by),
            })
    if not rows:
        return [cov, {"type": "unavailable", "title": title, "reason": "The analysed demos record no KOTH."}]
    us = [r for r in rows if r["completa"] == "This team"]
    them = [r for r in rows if r["completa"] == "Enemy"]
    none = [r for r in rows if r["completa"] == "Not completed"]
    return [cov,
            {"type": "text", "tone": "info",
             "text": f"Comeback: the team that completes the KOTH had {REGLA} when the cash-in started; «—» if there are no net worth samples."},
            {"type": "text", "tone": "confirmed",
             "text": f"{len(rows)} KOTH in {k} matches with demo: completed by this team {len(us)} "
                     f"({sum(1 for r in us if r['remontada'] == 'yes')} in comeback), by the enemy {len(them)} "
                     f"({sum(1 for r in them if r['remontada'] == 'yes')} in comeback), not completed {len(none)}."},
            {"type": "table", "title": "KOTH: who completes the cash-in", "n": k,
             "columns": [{"key": "match_id", "label": "Match"}, {"key": "n", "label": "#"},
                         {"key": "start_t", "label": "Start", "fmt": "mmss"}, {"key": "completed_t", "label": "Completed", "fmt": "mmss"},
                         {"key": "completa", "label": "Completed by", "objective": "KOTH"}, {"key": "remontada", "label": "In comeback"}],
             "rows": rows}]
