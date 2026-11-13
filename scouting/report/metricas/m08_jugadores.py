"""Jugadores de la plantilla: medias por partida, fase de líneas y zonas donde más mueren / matan."""
from collections import Counter

from .. import GRID, cell_name, metric
from ... import matches as M
from .m07_fase_lineas import _tied_max

MAX_MAPAS = 12


def _mean(v, nd=1):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), nd) if v else None


def _ranked(counter, limit=3):
    return sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))[:limit]


def _top(counter, fmt, limit=3):
    return ", ".join(f"{fmt(k)} ({v})" for k, v in _ranked(counter, limit)) or None


@metric("jugadores", "Players", order=80)
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
            a = acc.setdefault(key, {"account_id": p["account_id"], "name": (ident or {}).get("name") or f"Account {p['account_id']}",
                                      "items": [], "heroes": Counter(), "lanes": Counter(), "kc": Counter(), "dc": Counter(), "krc": Counter(), "drc": Counter()})
            a["items"].append((p, demo))
            a["heroes"][p["hero_id"]] += 1
            if p["lane"] is not None:
                a["lanes"][p["lane"]] += 1
            for c, r, k in p["kill_cells"]:
                a["kc"][(c, r)] += k
            for c, r, k in p["death_cells"]:
                a["dc"][(c, r)] += k
            for c, r, k in p["kill_cells_rest"] or []:
                a["krc"][(c, r)] += k
            for c, r, k in p["death_cells_rest"] or []:
                a["drc"][(c, r)] += k
    if not acc:
        return [{"type": "unavailable", "title": "Players", "reason": "No roster players in the analysed matches."}]
    players = sorted(acc.values(), key=lambda a: (-len(a["items"]), a["name"]))
    rows = []
    for a in players:
        its = [p for p, _ in a["items"]]
        dm = [p for p, d in a["items"] if d]
        rs = [p for p in its if p["kills_rest"] is not None]
        rows.append({"account_id": a["account_id"], "jugador": a["name"], "n": len(its),
                     "heroes": _top(a["heroes"], ctx.hero), "hero_ids": [h for h, _ in _ranked(a["heroes"]) if h is not None],
                     "lineas": _top(a["lanes"], lambda l: names.get(l, f"Lane {l}")),
                     "kills": _mean([p["kills"] for p in its]), "deaths": _mean([p["deaths"] for p in its]), "assists": _mean([p["assists"] for p in its]),
                     "kda": _mean([p["kda"] for p in its], 2),
                     "troopers_per_min": _mean([p["troopers_per_min"] for p in its], 2), "jungla_per_min": _mean([p["jungla_per_min"] for p in its], 2),
                     "nw_per_min": _mean([p["nw_per_min"] for p in its], 0), "nw_at_600": _mean([p["nw_at_600"] for p in its], 0),
                     "n_demo": len(dm),
                     "n_rest": len(rs), "kills_rest": _mean([p["kills_rest"] for p in rs]),
                     "deaths_rest": _mean([p["deaths_rest"] for p in rs]),
                     "lane_dmg_done": _mean([p["lane_dmg_done"] for p in dm], 0), "lane_dmg_taken": _mean([p["lane_dmg_taken"] for p in dm], 0),
                     "lane_kills": _mean([p["lane_kills"] for p in its]), "lane_deaths": _mean([p["lane_deaths"] for p in its]),
                     "ganks_made": _mean([p["ganks_made"] for p in dm]), "ganks_suffered": _mean([p["ganks_suffered"] for p in dm])})
    cols = [("jugador", "Player"), ("n", "Matches"), ("heroes", "Heroes"), ("lineas", "Lanes"), ("kills", "Kills"), ("deaths", "Deaths"),
            ("assists", "Assists"), ("kda", "Mean KDA"), ("troopers_per_min", "Troopers/min"), ("jungla_per_min", "Jungle/min"),
            ("nw_per_min", "Net worth/min"), ("nw_at_600", "NW at 10 min"), ("n_demo", "With demo"),
            ("n_rest", "Matches with demo (rest)"), ("kills_rest", "Kills without objective fights (mean)"),
            ("deaths_rest", "Deaths without objective fights (mean)"),
            ("lane_dmg_done", "Damage dealt (laning)"), ("lane_dmg_taken", "Damage taken (laning)"),
            ("lane_kills", "Kills (laning)"), ("lane_deaths", "Deaths (laning)"), ("ganks_made", "Ganks made"), ("ganks_suffered", "Ganks suffered")]
    extra = {"heroes": {"fmt": "heroes"}}
    for k in ("kills", "deaths", "assists", "troopers_per_min", "jungla_per_min", "nw_per_min", "nw_at_600",
              "kills_rest", "deaths_rest", "lane_dmg_done", "lane_dmg_taken"):
        extra[k] = {"bar": True}
    for k in ("nw_per_min", "nw_at_600", "lane_dmg_done", "lane_dmg_taken"):
        extra[k]["fmt"] = "int"
    blocks = [ctx.sample_warning(),
              {"type": "text", "tone": "info",
               "text": "Per-match means for each roster player (identity by linked player; otherwise by account). Laning phase = min 0–10. "
                       "Damage and ganks only average matches with demo (column «With demo»); what is missing shows as «–». "
                       "Kills/deaths without objective fights are per-match means over the matches with demo only (see the column Matches with demo (rest); KOTH is not identifiable without it)."},
              {"type": "table", "kind": "jugadores", "title": "Means per player", "n": ctx.n,
               "columns": [{"key": k, "label": l, **extra.get(k, {})} for k, l in cols], "rows": rows}]
    tied = _tied_max(rows, "kills")
    cards = [{"title": "Most kills per match" + (" (tie)" if len(tied) > 1 else ""), "value": r["kills"], "fmt": "1", "unit": "kills (mean)", "sub": r["jugador"],
              "hero_ids": r["hero_ids"], "n": r["n"]} for r in tied]
    if cards:
        blocks.insert(2, {"type": "cards", "kind": "player_cards", "items": cards})

    def zonas(a, cells, title, side, n=None):
        top = sorted(cells.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        if not top:
            return None
        return {"type": "table", "kind": "zonas", "title": f"{a['name']}: {title}", "n": len(a["items"]) if n is None else n,
                "note": "Zones = cells of the map grid, with the own base at the bottom (normalized).",
                "map": {"grid": GRID, "normalized": True, "layers": [{"kind": "highlight", "name": title, "side": side,
                                                                      "cells": [[c, r, cell_name((c, r))] for (c, r), _ in top]}]},
                "columns": [{"key": "zona", "label": "Zone (see map)"}, {"key": "eventos", "label": "Total", "bar": True}],
                "rows": [{"zona": cell_name(c), "eventos": v} for c, v in top]}

    for a in players[:MAX_MAPAS]:
        nr = sum(1 for p, _ in a["items"] if p["kills_rest"] is not None)
        blocks += [zonas(a, a["dc"], "zones where they die most", "them"), zonas(a, a["kc"], "zones where they kill most", "us"),
                   zonas(a, a["drc"], "zones where they die most (without objective fights)", "them", nr),
                   zonas(a, a["krc"], "zones where they kill most (without objective fights)", "us", nr)]
    if len(players) > MAX_MAPAS:
        blocks.append({"type": "text", "tone": "info", "text": f"Zone maps only for the {MAX_MAPAS} players with most matches."})
    return blocks
