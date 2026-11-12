"""Midboss: cuándo, quién, contexto (kills y net worth) y robos."""
from collections import Counter

from .. import metric, stats
from ... import matches as M


def _context(nw_diff, margin):
    if nw_diff is None:
        return "sin datos"
    if nw_diff > margin:
        return "ventaja"
    if nw_diff < -margin:
        return "desventaja"
    return "igualdad"


@metric("midboss", "Midboss", order=40)
def midboss(ctx):
    win = int(ctx.params.get("midboss_window_s") or 90)
    margin = float(ctx.params.get("nw_margin") or 3000)
    events = []
    matches_with = 0
    first_by = Counter()
    for m in ctx.matches:
        mb = M.midboss(m.mi)
        if mb:
            matches_with += 1
            first_by[m.rel(mb[0]["team_killed"])] += 1
        for e in mb:
            t = e["t"] or 0
            k_us = sum(1 for d in m.deaths if d["killer_team"] == m.our and d["victim_team"] == m.their and t - win <= (d["t"] or 0) <= t)
            k_them = sum(1 for d in m.deaths if d["killer_team"] == m.their and d["victim_team"] == m.our and t - win <= (d["t"] or 0) <= t)
            cum_us = sum(1 for d in m.deaths if d["killer_team"] == m.our and d["victim_team"] == m.their and (d["t"] or 0) <= t)
            cum_them = sum(1 for d in m.deaths if d["killer_team"] == m.their and d["victim_team"] == m.our and (d["t"] or 0) <= t)
            nw = M.team_networth_at(m.mi, m.our, t) - M.team_networth_at(m.mi, m.their, t)
            events.append({
                "match_id": m.id, "n": e["n"], "t": t, "killer": m.rel(e["team_killed"]), "claimer": m.rel(e["team_claimed"]),
                "stolen": e["stolen"], "kills_us": k_us, "kills_them": k_them, "kill_adv": cum_us - cum_them,
                "nw_adv": round(nw), "context": _context(nw, margin), "won": m.won,
            })
    n = ctx.n
    blocks = [ctx.sample_warning(),
              {"type": "unavailable", "title": "Cristales del Midboss, quién lo inicia e intentos fallidos",
               "reason": "La API no registra estos datos: solo da quién lo mató, quién lo reclamó y el segundo."},
              {"type": "text", "tone": "interpretation",
               "text": "«Reclamado» (team_claimed) no está documentado. Interpretación: si lo reclama un equipo distinto del que lo mató, es un robo."},
              {"type": "text", "tone": "info",
               "text": f"Ventana de kills previas: {win} s. Contexto por net worth en ese segundo (interpolado de las muestras cada pocos minutos): "
                       f"ventaja > +{margin:.0f}, desventaja < −{margin:.0f}, si no igualdad."}]
    if not events:
        blocks.append({"type": "text", "tone": "confirmed", "text": f"No hay Midboss en ninguna de las {n} partidas."})
        return blocks
    ours = [e for e in events if e["killer"] == "us"]
    theirs = [e for e in events if e["killer"] == "them"]
    blocks.append({"type": "text", "tone": "confirmed",
                   "text": f"Midboss en {matches_with} de {n} partidas ({len(events)} muertes del Midboss). Lo mata este equipo {len(ours)} veces y el rival {len(theirs)}. "
                           f"El primero de la partida: este equipo {first_by['us']}, rival {first_by['them']}."})
    rows = []
    for label, evs in (("Este equipo", ours), ("Rival", theirs), ("Primer Midboss de este equipo", [e for e in ours if e["n"] == 1]),
                       ("Primer Midboss del rival", [e for e in theirs if e["n"] == 1])):
        s = stats([e["t"] for e in evs])
        rows.append({"quien": label, "veces": len(evs), "media": s["mean"], "mediana": s["median"], "min": s["min"], "max": s["max"]})
    blocks.append({"type": "table", "title": "Minuto del Midboss", "n": n,
                   "columns": [{"key": "quien", "label": "Lo mata"}, {"key": "veces", "label": "Veces"}, {"key": "media", "label": "Media", "fmt": "mmss"},
                               {"key": "mediana", "label": "Mediana", "fmt": "mmss"}, {"key": "min", "label": "Mín.", "fmt": "mmss"}, {"key": "max", "label": "Máx.", "fmt": "mmss"}],
                   "rows": rows})
    blocks.append({"type": "histogram", "title": "Minuto del Midboss", "bin_s": 120, "n": n,
                   "series": [{"name": "Este equipo", "side": "us", "values": [e["t"] for e in ours]}, {"name": "Rival", "side": "them", "values": [e["t"] for e in theirs]}]})
    scen = []
    for label, evs in (("Cuando lo mata este equipo", ours), ("Cuando lo mata el rival", theirs)):
        if not evs:
            scen.append({"escenario": label, "veces": 0})
            continue
        ctxc = Counter(e["context"] for e in evs)
        scen.append({
            "escenario": label, "veces": len(evs),
            "kills_us": stats([e["kills_us"] for e in evs])["mean"], "kills_them": stats([e["kills_them"] for e in evs])["mean"],
            "kill_adv": stats([e["kill_adv"] for e in evs])["median"], "nw_adv": stats([e["nw_adv"] for e in evs])["median"],
            "ventaja": ctxc["ventaja"], "igualdad": ctxc["igualdad"], "desventaja": ctxc["desventaja"],
            "robos": sum(1 for e in evs if e["stolen"]),
            "ganadas": sum(1 for e in evs if e["won"]),
        })
    blocks.append({"type": "table", "title": "Escenarios (desde el punto de vista de este equipo)", "n": n,
                   "note": "Robos: veces que lo reclama el equipo que NO lo mató (interpretación).",
                   "columns": [{"key": "escenario", "label": "Escenario"}, {"key": "veces", "label": "Veces"},
                               {"key": "kills_us", "label": f"Kills propias en {win}s (media)", "fmt": "1"},
                               {"key": "kills_them", "label": f"Kills rivales en {win}s (media)", "fmt": "1"},
                               {"key": "kill_adv", "label": "Ventaja de kills (mediana)", "fmt": "signed"},
                               {"key": "nw_adv", "label": "Ventaja net worth (mediana)", "fmt": "signed0"},
                               {"key": "ventaja", "label": "En ventaja"}, {"key": "igualdad", "label": "Igualdad"}, {"key": "desventaja", "label": "Desventaja"},
                               {"key": "robos", "label": "Reclamado por el otro equipo"}, {"key": "ganadas", "label": "Partidas ganadas"}],
                   "rows": scen})
    blocks.append({"type": "bars", "title": "Contexto al matar el Midboss", "n": n, "unit": "",
                   "labels": ["ventaja", "igualdad", "desventaja"],
                   "series": [{"name": "Este equipo", "side": "us", "values": [sum(1 for e in ours if e["context"] == c) for c in ("ventaja", "igualdad", "desventaja")]},
                              {"name": "Rival", "side": "them", "values": [sum(1 for e in theirs if e["context"] == c) for c in ("ventaja", "igualdad", "desventaja")]}]})
    blocks.append({"type": "table", "title": "Detalle", "n": n,
                   "columns": [{"key": "match_id", "label": "Partida"}, {"key": "n", "label": "#"}, {"key": "t", "label": "Minuto", "fmt": "mmss"},
                               {"key": "killer_txt", "label": "Lo mata"}, {"key": "claimer_txt", "label": "Lo reclama"},
                               {"key": "kills_us", "label": "Kills propias"}, {"key": "kills_them", "label": "Kills rival"},
                               {"key": "kill_adv", "label": "Ventaja kills", "fmt": "signed"}, {"key": "nw_adv", "label": "Ventaja NW", "fmt": "signed0"},
                               {"key": "context", "label": "Contexto"}],
                   "rows": [dict(e, killer_txt="Este equipo" if e["killer"] == "us" else "Rival",
                                 claimer_txt=("Este equipo" if e["claimer"] == "us" else "Rival") + (" (robo)" if e["stolen"] else "")) for e in events]})
    # patrones
    if n >= 3:
        if len(ours) >= 3:
            c = Counter(e["context"] for e in ours).most_common(1)[0]
            if c[1] / len(ours) >= 0.6:
                ctx.finding("pattern", f"Suelen hacer el Midboss en {c[0]} de net worth ({c[1]} de {len(ours)} veces).", c[1], len(ours))
        steals_them = sum(1 for e in ours if e["stolen"])
        if steals_them >= 2:
            ctx.finding("weakness", f"Les reclaman el Midboss que matan ellos {steals_them} de {len(ours)} veces (posible robo; interpretación).", steals_them, len(ours), confirmed=False)
        steals_us = sum(1 for e in theirs if e["stolen"])
        if steals_us >= 2:
            ctx.finding("strength", f"Reclaman el Midboss que mata el rival {steals_us} de {len(theirs)} veces (posible robo; interpretación).", steals_us, len(theirs), confirmed=False)
        if first_by["them"] / n >= 0.6:
            ctx.finding("opportunity", f"El rival mata el primer Midboss en {first_by['them']} de {n} partidas: disputarlo antes o controlar la zona.", first_by["them"], n, confirmed=False)
        if first_by["us"] / n >= 0.6:
            ctx.finding("strength", f"Se llevan el primer Midboss en {first_by['us']} de {n} partidas.", first_by["us"], n)
    return blocks
