"""Jugadores de la plantilla: medias por partida, fase de líneas y zonas donde más mueren / matan."""
from collections import Counter

from .. import GRID, cell_name, metric
from ... import matches as M

MAX_MAPAS = 12


def _mean(v, nd=1):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), nd) if v else None


def _top(counter, fmt, limit=3):
    return ", ".join(f"{fmt(k)} ({v})" for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))[:limit]) or None


@metric("jugadores", "Jugadores", order=80)
def jugadores(ctx):
    names = {int(k): v["nombre"] for k, v in M.lanes_payload().items()}
    acc = {}
    for m in ctx.matches:
        demo = m.lane_phase["source"] == "demo"
        for p in m.player_stats:
            if p["team"] != m.our:
                continue
            ident = ctx.player_ids.get(p["account_id"])
            key = ("p", ident["player_id"]) if ident and ident.get("player_id") is not None else ("a", p["account_id"])
            a = acc.setdefault(key, {"account_id": p["account_id"], "name": (ident or {}).get("name") or f"Cuenta {p['account_id']}",
                                      "items": [], "heroes": Counter(), "lanes": Counter(), "kc": Counter(), "dc": Counter()})
            a["items"].append((p, demo))
            a["heroes"][p["hero_id"]] += 1
            if p["lane"] is not None:
                a["lanes"][p["lane"]] += 1
            for c, r, k in p["kill_cells"]:
                a["kc"][(c, r)] += k
            for c, r, k in p["death_cells"]:
                a["dc"][(c, r)] += k
    if not acc:
        return [{"type": "unavailable", "title": "Jugadores", "reason": "No hay jugadores de la plantilla en las partidas analizadas."}]
    players = sorted(acc.values(), key=lambda a: (-len(a["items"]), a["name"]))
    rows = []
    for a in players:
        its = [p for p, _ in a["items"]]
        dm = [p for p, d in a["items"] if d]
        rows.append({"account_id": a["account_id"], "jugador": a["name"], "n": len(its),
                     "heroes": _top(a["heroes"], ctx.hero), "lineas": _top(a["lanes"], lambda l: names.get(l, f"Carril {l}")),
                     "kills": _mean([p["kills"] for p in its]), "deaths": _mean([p["deaths"] for p in its]), "assists": _mean([p["assists"] for p in its]),
                     "kda": _mean([p["kda"] for p in its], 2),
                     "troopers_per_min": _mean([p["troopers_per_min"] for p in its], 2), "jungla_per_min": _mean([p["jungla_per_min"] for p in its], 2),
                     "nw_per_min": _mean([p["nw_per_min"] for p in its], 0), "nw_at_600": _mean([p["nw_at_600"] for p in its], 0),
                     "n_demo": len(dm),
                     "lane_dmg_done": _mean([p["lane_dmg_done"] for p in dm], 0), "lane_dmg_taken": _mean([p["lane_dmg_taken"] for p in dm], 0),
                     "lane_kills": _mean([p["lane_kills"] for p in its]), "lane_deaths": _mean([p["lane_deaths"] for p in its]),
                     "ganks_made": _mean([p["ganks_made"] for p in dm]), "ganks_suffered": _mean([p["ganks_suffered"] for p in dm])})
    cols = [("jugador", "Jugador"), ("n", "Partidas"), ("heroes", "Héroes"), ("lineas", "Líneas"), ("kills", "Kills"), ("deaths", "Muertes"),
            ("assists", "Asist."), ("kda", "KDA medio"), ("troopers_per_min", "Tropas/min"), ("jungla_per_min", "Jungla/min"),
            ("nw_per_min", "Net worth/min"), ("nw_at_600", "NW a los 10"), ("n_demo", "Con demo"),
            ("lane_dmg_done", "Daño hecho (líneas)"), ("lane_dmg_taken", "Daño recibido (líneas)"),
            ("lane_kills", "Kills (líneas)"), ("lane_deaths", "Muertes (líneas)"), ("ganks_made", "Gankeos hechos"), ("ganks_suffered", "Gankeos sufridos")]
    blocks = [ctx.sample_warning(),
              {"type": "text", "tone": "info",
               "text": "Medias por partida de cada jugador de la plantilla (identidad por jugador enlazado; si no, por cuenta). Fase de líneas = min 0–10. "
                       "Daño y gankeos solo promedian partidas con demo (columna «Con demo»); lo que falta se muestra «–»."},
              {"type": "table", "kind": "jugadores", "title": "Medias por jugador", "n": ctx.n,
               "columns": [{"key": k, "label": l} for k, l in cols], "rows": rows}]

    def zonas(a, cells, title, side):
        top = sorted(cells.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        if not top:
            return None
        return {"type": "table", "kind": "zonas", "title": f"{a['name']}: {title}", "n": len(a["items"]),
                "note": "Zonas = celdas de la cuadrícula del mapa, con la base propia abajo (normalizado).",
                "map": {"grid": GRID, "normalized": True, "layers": [{"kind": "highlight", "name": title, "side": side,
                                                                      "cells": [[c, r, cell_name((c, r))] for (c, r), _ in top]}]},
                "columns": [{"key": "zona", "label": "Zona (ver mapa)"}, {"key": "eventos", "label": "Total"}],
                "rows": [{"zona": cell_name(c), "eventos": v} for c, v in top]}

    for a in players[:MAX_MAPAS]:
        blocks += [zonas(a, a["dc"], "zonas donde más muere", "them"), zonas(a, a["kc"], "zonas donde más mata", "us")]
    if len(players) > MAX_MAPAS:
        blocks.append({"type": "text", "tone": "info", "text": f"Mapas de zonas solo de los {MAX_MAPAS} jugadores con más partidas."})
    return blocks
