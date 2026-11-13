"""Desglose por jugador de una partida: KDA, economía, daño, fase de líneas y mapa de kills/muertes."""
from . import matches
from .minimap import load_calibration
from .report import cell_of


def _cells(points, team, cal):
    """[[col, row, n]] con las posiciones (x, y) dadas, giradas 180° para el equipo 1 (base propia abajo).
    Las posiciones ausentes o fuera de la cuadrícula no cuentan."""
    cnt = {}
    for x, y in points:
        if x is None or y is None:
            continue
        if team == 1:
            x, y = -x, -y
        c = cell_of(x, y, cal)
        if c is not None:
            cnt[c] = cnt.get(c, 0) + 1
    return [[c, r, n] for (c, r), n in sorted(cnt.items())]


def _count(events):
    out = {"midboss": 0, "koth": 0, "rest": 0, "unknown": 0}
    for x in events:
        out[x["fight"]] += 1
    return out


def _final(p, field, dur):
    v = matches.stat_at(p, field, dur)
    return None if v is None else int(round(v))


def player_stats(mi, lane_phase_result, cal=None, fights=None):
    """Lista por jugador (orden equipo, slot). Dato ausente -> None. Los campos de fase de líneas
    (lane, dmg_done, dmg_taken, ganks_made, ganks_suffered, deaths, kills) se copian de `lane_phase_result`
    con prefijo `lane_` salvo `lane`; kill_cells y death_cells usan la posición de la muerte de la víctima (como el informe: kill = lugar donde murió el rival)."""
    cal = cal or load_calibration()
    # resultado de fights.classify: sin él (o sin KOTH identificable) los campos "resto" son None
    ev = (fights or {}).get("events") if fights and fights.get("koth_known") else None
    dur = mi.get("duration_s") or 0
    eco = {e["slot"]: e for e in matches.economy(mi)["players"]}
    ds = matches.deaths(mi)
    lp = (lane_phase_result or {}).get("players") or {}
    ds_f = ev if ev is not None else []
    out = []
    for p in sorted(mi.get("players") or [], key=lambda p: (p.get("team"), p.get("player_slot"))):
        s, tm = p.get("player_slot"), p.get("team")
        e = eco.get(s) or {}
        pm = e.get("per_min") or {}
        k, d, a = p.get("kills"), p.get("deaths"), p.get("assists")
        kda = round((k + a) / max(d, 1), 2) if None not in (k, d, a) else None
        l = lp.get(str(s)) or {}
        kev = [x for x in ds_f if x["killer_slot"] == s and x["killer_team"] != x["victim_team"]]
        dev = [x for x in ds_f if x["victim_slot"] == s]
        kr = [x for x in kev if x["fight"] == "rest"]
        dr = [x for x in dev if x["fight"] == "rest"]
        out.append({
            "slot": s, "team": tm, "account_id": p.get("account_id"), "hero_id": p.get("hero_id"),
            "lane": l.get("lane"),
            "kills": k, "deaths": d, "assists": a, "kda": kda,
            "last_hits": p.get("last_hits"), "denies": p.get("denies"),
            "net_worth": p.get("net_worth"), "nw_per_min": pm.get("net_worth"),
            "nw_at_600": _final(p, "net_worth", 600),
            "troopers_per_min": pm.get("troopers_kills"), "jungla_per_min": pm.get("jungla_kills"),
            "sources": e.get("sources") if p.get("stats") else None,
            "player_damage": _final(p, "player_damage", dur), "damage_taken": _final(p, "player_damage_taken", dur),
            "kill_cells": _cells([(x["x"], x["y"]) for x in ds
                                  if x["killer_slot"] == s and x["killer_team"] != x["victim_team"]], tm, cal),
            "death_cells": _cells([(x["x"], x["y"]) for x in ds if x["victim_slot"] == s], tm, cal),
            "kills_rest": len(kr) if ev is not None else None, "deaths_rest": len(dr) if ev is not None else None,
            "kill_cells_rest": _cells([(x["x"], x["y"]) for x in kr], tm, cal) if ev is not None else None,
            "death_cells_rest": _cells([(x["x"], x["y"]) for x in dr], tm, cal) if ev is not None else None,
            "fights": {"kills": _count(kev), "deaths": _count(dev)} if ev is not None else None,
            "lane_dmg_done": l.get("dmg_done"), "lane_dmg_taken": l.get("dmg_taken"),
            "ganks_made": l.get("ganks_made"), "ganks_suffered": l.get("ganks_suffered"),
            "lane_deaths": l.get("deaths"), "lane_kills": l.get("kills"),
        })
    return out
