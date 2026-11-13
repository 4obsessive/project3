"""Kills y muertes sobre el minimapa: puntos, zonas con más muertes/kills y balance por zona."""
from collections import defaultdict

from .. import GRID, cell_name, cell_of, metric
from ...minimap import load_calibration


@metric("mapa", "Kills y muertes en el minimapa", order=20)
def mapa(ctx):
    cal = ctx.calibration or load_calibration()
    normalize = bool(ctx.params.get("normalize"))
    kills_pts, death_pts = [], []
    cell_k, cell_d = defaultdict(int), defaultdict(int)
    match_k, match_d = defaultdict(set), defaultdict(set)
    for m in ctx.matches:
        for e in m.deaths:
            if e["x"] is None:
                continue
            x, y = m.norm(e["x"], e["y"], normalize)
            c = cell_of(x, y, cal)
            if e["victim_team"] == m.our:
                death_pts.append([round(x), round(y), m.id, e["t"]])
                if c:
                    cell_d[c] += 1
                    match_d[c].add(m.id)
            elif e["killer_team"] == m.our:
                kills_pts.append([round(x), round(y), m.id, e["t"]])
                if c:
                    cell_k[c] += 1
                    match_k[c].add(m.id)
    # sin peleas de midboss ni KOTH: solo partidas con demo (sin él el KOTH no se identifica)
    rk_pts, rd_pts = [], []
    rcell_k, rcell_d = defaultdict(int), defaultdict(int)
    rmatch_k, rmatch_d = defaultdict(set), defaultdict(set)
    split = {t: [0, 0] for t in ("midboss", "koth", "rest", "unknown")}  # [kills, muertes]
    incl = excl = 0
    for m in ctx.matches:
        fx = m.fights
        if not fx["koth_known"]:
            excl += 1
            continue
        incl += 1
        for e in fx["events"]:
            side = 1 if e["victim_team"] == m.our else 0 if e["killer_team"] == m.our else None
            if side is None:
                continue
            split[e["fight"]][side] += 1
            if e["fight"] != "rest":
                continue
            x, y = m.norm(e["x"], e["y"], normalize)
            c = cell_of(x, y, cal)
            if side:
                rd_pts.append([round(x), round(y), m.id, e["t"]])
                if c:
                    rcell_d[c] += 1
                    rmatch_d[c].add(m.id)
            else:
                rk_pts.append([round(x), round(y), m.id, e["t"]])
                if c:
                    rcell_k[c] += 1
                    rmatch_k[c].add(m.id)
    cells = set(cell_k) | set(cell_d)
    balance = [[c[0], c[1], cell_k[c] - cell_d[c]] for c in cells]
    note = ("Normalizado: las partidas jugadas como equipo 1 se giran 180° para que la base propia quede siempre abajo."
            if normalize else "Sin normalizar: cada punto está en su posición real del mapa (equipo 0 abajo).")
    blocks = [
        ctx.sample_warning(),
        {"type": "text", "tone": "info",
         "text": f"Kill = lugar donde murió el rival a manos de este equipo. Muerte = lugar donde murió un jugador del equipo. {note}"},
        {"type": "map", "title": "Kills (●) y muertes (✕)", "n": ctx.n, "normalized": normalize, "grid": GRID,
         "layers": [
             {"kind": "points", "name": f"Kills ({len(kills_pts)})", "side": "us", "points": kills_pts},
             {"kind": "crosses", "name": f"Muertes ({len(death_pts)})", "side": "them", "points": death_pts},
         ]},
        {"type": "map", "title": "Balance por zona (kills − muertes)", "n": ctx.n, "normalized": normalize, "grid": GRID,
         "layers": [{"kind": "cells", "name": "Balance", "cells": balance, "diverging": True, "labels": True}]},
    ]

    def zone_map(cells_list, side, name):
        """Mapa que acompaña a una tabla: resalta las celdas de sus filas, en el mismo orden. Celda = [col, fila, zona(, lado)]."""
        return {"grid": GRID, "normalized": normalize,
                "layers": [{"kind": "highlight", "name": name, "side": side, "cells": cells_list}]}

    def top(counter, matches_by_cell, label, side, n=None):
        n = ctx.n if n is None else n
        rows, hl = [], []
        for c, v in sorted(counter.items(), key=lambda kv: -kv[1])[:6]:
            rows.append({"zona": cell_name(c), "eventos": v, "partidas": len(matches_by_cell[c]),
                         "pct": round(100 * len(matches_by_cell[c]) / n)})
            hl.append([c[0], c[1], cell_name(c)])
        return {"type": "table", "title": label, "n": n, "note": "Zonas = celdas de la cuadrícula dibujada sobre el mapa.",
                "map": zone_map(hl, side, label),
                "columns": [{"key": "zona", "label": "Zona (ver mapa)"}, {"key": "eventos", "label": "Total"},
                            {"key": "partidas", "label": "Partidas en que ocurre"}, {"key": "pct", "label": "% partidas"}],
                "rows": rows}

    blocks.append(top(cell_d, match_d, "Zonas con más muertes", "them"))
    blocks.append(top(cell_k, match_k, "Zonas con más kills", "us"))
    bal_rows = sorted(({"zona": cell_name(c), "kills": cell_k[c], "muertes": cell_d[c], "balance": cell_k[c] - cell_d[c], "_c": c} for c in cells),
                      key=lambda r: r["balance"])
    if bal_rows:
        shown = bal_rows[:4] + [r for r in bal_rows[-4:][::-1] if r not in bal_rows[:4]]
        hl = [[r["_c"][0], r["_c"][1], r["zona"], "us" if r["balance"] > 0 else "them" if r["balance"] < 0 else "neutral"] for r in shown]
        blocks.append({"type": "table", "title": "Dónde ganan y pierden enfrentamientos", "n": ctx.n,
                       "columns": [{"key": "zona", "label": "Zona (ver mapa)"}, {"key": "kills", "label": "Kills"},
                                   {"key": "muertes", "label": "Muertes"}, {"key": "balance", "label": "Balance"}],
                       "map": zone_map(hl, "us", "Balance por zona"),
                       "rows": [{k: v for k, v in r.items() if k != "_c"} for r in shown]})
    blocks += _sin_objetivos(ctx, normalize, incl, excl, split, rk_pts, rd_pts, rcell_k, rcell_d, rmatch_k, rmatch_d, top)
    # patrones: zonas donde mueren en al menos la mitad de las partidas y con balance negativo
    if normalize and ctx.n >= 3:
        # solo las 3 zonas más marcadas de cada tipo, para no llenar las conclusiones de ruido
        weak = sorted((c for c in cells if len(match_d[c]) / ctx.n >= 0.5 and cell_d[c] > cell_k[c]), key=lambda c: cell_k[c] - cell_d[c])[:3]
        for c in weak:
            ctx.finding("weakness", f"Mueren repetidamente en la zona {cell_name(c)} del mapa ({cell_d[c]} muertes vs {cell_k[c]} kills; en {len(match_d[c])} de {ctx.n} partidas).", len(match_d[c]), ctx.n)
        strong = sorted((c for c in cells if len(match_k[c]) / ctx.n >= 0.5 and cell_k[c] >= 2 * max(cell_d[c], 1)), key=lambda c: cell_d[c] - cell_k[c])[:3]
        for c in strong:
            ctx.finding("strength", f"Ganan peleas de forma repetida en la zona {cell_name(c)} del mapa ({cell_k[c]} kills vs {cell_d[c]} muertes; en {len(match_k[c])} de {ctx.n} partidas).", len(match_k[c]), ctx.n)
    else:
        blocks.append({"type": "text", "tone": "info", "text": "Las conclusiones por zona solo se generan con el lado normalizado (si no, las zonas mezclan bases distintas)."})
    return blocks


def _sin_objetivos(ctx, normalize, incl, excl, split, rk_pts, rd_pts, rcell_k, rcell_d, rmatch_k, rmatch_d, top):
    """Bloques de kills y muertes sin peleas de midboss ni KOTH (solo conteos; sin posición = fuera de los mapas)."""
    out = [{"type": "text", "tone": "info" if not excl else "warning", "kind": "fight_excluded",
            "text": (f"Without midboss and KOTH fights: {excl} of {ctx.n} matches excluded (KOTH not identifiable without demo)."
                     if excl else f"Without midboss and KOTH fights: all {ctx.n} matches have demo data.")}]
    if not incl:
        return out
    names = {"midboss": "Midboss fights", "koth": "KOTH fights", "rest": "Rest (no objective fight)", "unknown": "No position (not on maps)"}
    rows = [{"tipo": t, "label": names[t], "kills": k, "deaths": d, "total": k + d} for t, (k, d) in split.items()]
    tot = [sum(v[i] for v in split.values()) for i in (0, 1)]
    rows.append({"tipo": "total", "label": "Total", "kills": tot[0], "deaths": tot[1], "total": sum(tot)})
    out.append({"type": "table", "kind": "fight_split", "title": f"Kills and deaths by fight type ({incl} matches with demo)", "n": incl,
                "note": "Kill = place where the rival died; midboss within 2500 units of the pit, KOTH within 2000 of a rift (see Decisions in the spec).",
                "columns": [{"key": "label", "label": "Fight type"}, {"key": "kills", "label": "Kills"},
                            {"key": "deaths", "label": "Deaths"}, {"key": "total", "label": "Total"}],
                "rows": rows})
    out.append({"type": "map", "kind": "rest_map", "title": "Kills (●) and deaths (✕) without midboss and KOTH fights", "n": incl,
                "normalized": normalize, "grid": GRID,
                "layers": [{"kind": "points", "name": f"Kills ({len(rk_pts)})", "side": "us", "points": rk_pts},
                           {"kind": "crosses", "name": f"Deaths ({len(rd_pts)})", "side": "them", "points": rd_pts}]})
    out.append(top(rcell_d, rmatch_d, "Zones with most deaths (without objective fights)", "them", incl))
    out.append(top(rcell_k, rmatch_k, "Zones with most kills (without objective fights)", "us", incl))
    return out
