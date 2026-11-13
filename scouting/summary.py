"""Resúmenes de jugador materializados (se recalculan tras cada actualización o edición)."""
import json
import threading

from . import roles as roles_mod
from . import images, scoring
from . import stats as stats_mod
from .db import kv_get

_cache_lock = threading.Lock()
_cache = {"version": 0, "body": None}

HERO_PRIOR_N = 20
ROLE_MIN_MATCHES = 10


def reliability(matches):
    return stats_mod.reliability(matches)


def hero_names(con):
    raw = kv_get(con, "hero_names")
    return {int(k): v for k, v in json.loads(raw).items()} if raw else {}


def effective_team(con):
    """{player_id: (equipo, origen)}: el campo manual manda sobre equipos.txt."""
    out = {}
    for r in con.execute(
        "SELECT a.player_id, tr.team FROM team_rosters tr JOIN accounts a ON a.account_id=tr.account_id ORDER BY tr.line_no"
    ):
        out.setdefault(r["player_id"], (r["team"], "equipos.txt"))
    for r in con.execute("SELECT player_id, team FROM manual WHERE team IS NOT NULL AND TRIM(team)<>''"):
        out[r["player_id"]] = (r["team"].strip(), "manual")
    return out


def _latest_snapshots(con):
    """Último snapshot por leaderboard_id: {lid: (snapshot_id, taken_at, season)}"""
    out = {}
    for r in con.execute(
        "SELECT s.leaderboard_id, s.id, s.taken_at, s.season FROM lb_snapshots s "
        "JOIN (SELECT leaderboard_id, MAX(taken_at) t FROM lb_snapshots GROUP BY leaderboard_id) m "
        "ON m.leaderboard_id IS s.leaderboard_id AND m.t=s.taken_at"
    ):
        out[r[0]] = (r[1], r[2], r[3])
    return out


def _kv_json(con, key):
    raw = kv_get(con, key)
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def _empty_acc():
    return {"m": 0, "w": 0, "k": 0, "d": 0, "a": 0, "dmg": 0, "t": 0, "objm": 0.0, "nwm": 0.0, "last": 0}


def _gather(con, ids):
    """Acumulados por héroe de un conjunto de cuentas."""
    heroes = {}
    if not ids:
        return heroes
    for r in con.execute("SELECT * FROM hero_stats WHERE account_id IN (%s)" % ",".join("?" * len(ids)), ids):
        h = heroes.setdefault(r["hero_id"], _empty_acc())
        t = r["time_played"] or 0
        h["m"] += r["matches"] or 0
        h["w"] += r["wins"] or 0
        h["k"] += r["kills"] or 0
        h["d"] += r["deaths"] or 0
        h["a"] += r["assists"] or 0
        h["dmg"] += r["player_damage"] or 0
        h["t"] += t
        h["objm"] += (r["obj_damage_per_min"] or 0) * t / 60.0
        h["nwm"] += (r["networth_per_min"] or 0) * t / 60.0
        h["last"] = max(h["last"], r["last_played"] or 0)
    return heroes


def build_all(con, player_ids=None):
    """Resúmenes por jugador. Dos pasadas: (1) acumulados de todos los jugadores para los priors
    de la población y las bases por héroe; (2) valores derivados (ajustados, índices, score)."""
    names = hero_names(con)
    table, threshold = roles_mod.load_table()
    roles_by_hero = roles_mod.hero_roles(table, names)
    current_lid = kv_get(con, "current_leaderboard_id")
    current_lid = int(current_lid) if current_lid else None
    teams = effective_team(con)
    latest = _latest_snapshots(con)
    population = {int(k): v for k, v in _kv_json(con, "hero_baselines_pop").items()}
    window = {"start": int(kv_get(con, "stats_window_start", 0) or 0) or None,
              "end": int(kv_get(con, "stats_window_end", 0) or 0) or None,
              "match_mode": kv_get(con, "stats_match_mode") or None}

    ranks = {}  # player_id -> {lid: rank}
    for lid, (sid, _t, _s) in latest.items():
        for r in con.execute("SELECT player_id, MIN(rank) FROM lb_entries WHERE snapshot_id=? AND player_id IS NOT NULL GROUP BY player_id", (sid,)):
            ranks.setdefault(r[0], {})[lid] = r[1]

    first_in_current = {}
    hist_start = None
    if current_lid is not None:
        for r in con.execute(
            "SELECT e.player_id, MIN(s.taken_at) FROM lb_entries e JOIN lb_snapshots s ON s.id=e.snapshot_id "
            "WHERE s.leaderboard_id=? AND e.player_id IS NOT NULL GROUP BY e.player_id", (current_lid,)
        ):
            first_in_current[r[0]] = r[1]
        hist_start = con.execute("SELECT MIN(taken_at) FROM lb_snapshots WHERE leaderboard_id=?", (current_lid,)).fetchone()[0]

    steam = {r["account_id"]: dict(r) for r in con.execute("SELECT * FROM steam_profiles")}
    badges = {}
    for r in con.execute(
        "SELECT b.account_id, b.badge, b.flat_progress FROM badge_history b JOIN "
        "(SELECT account_id, MAX(taken_at) t FROM badge_history GROUP BY account_id) m ON m.account_id=b.account_id AND m.t=b.taken_at"
    ):
        badges[r[0]] = (r[1], r[2])
    stats7 = {}
    for r in con.execute("SELECT account_id, SUM(matches), SUM(wins) FROM hero_stats_7d GROUP BY account_id"):
        stats7[r[0]] = (r[1] or 0, r[2] or 0)

    # ---------------------------------------------- pasada 1: acumulados de TODOS los jugadores
    all_players = con.execute("SELECT * FROM players").fetchall()
    gathered = {}
    for p in all_players:
        accts = [dict(r) for r in con.execute("SELECT account_id, source, steam_name, badge FROM accounts WHERE player_id=? ORDER BY account_id=? DESC, account_id", (p["id"], p["primary_account_id"]))]
        gathered[p["id"]] = (p, accts, _gather(con, [a["account_id"] for a in accts]))
    base = scoring.baselines([g[2] for g in gathered.values()], population)
    prior_m, prior_n = stats_mod.beta_prior([(sum(h["w"] for h in g[2].values()), sum(h["m"] for h in g[2].values())) for g in gathered.values()])
    hero_prior = {}
    pooled = {}
    for g in gathered.values():
        for hid, h in g[2].items():
            x = pooled.setdefault(hid, [0, 0])
            x[0] += h["w"]
            x[1] += h["m"]
    for hid, (w, m) in pooled.items():
        hero_prior[hid] = w / m if m else 0.5

    # ---------------------------------------------- pasada 2: derivados
    rows = []
    for pid, (p, accts, heroes) in gathered.items():
        tot = {k: sum(h[k] for h in heroes.values()) for k in ("m", "w", "k", "d", "a", "dmg", "t", "objm", "nwm")}
        m = tot["m"]
        lo, hi = stats_mod.wilson(tot["w"], m)
        wr_adj = stats_mod.shrink_rate(tot["w"], m, prior_m, prior_n)
        idx = scoring.player_indices(heroes, base)
        # banda del score: intervalo de la tasa ya encogida (cuentas ficticias del prior incluidas)
        alo, ahi = stats_mod.wilson(tot["w"] + prior_m * prior_n, m + prior_n)
        rows.append({"pid": pid, "n": m, "wr_adj": wr_adj, "wr_lo": alo, "wr_hi": ahi, "raw_lo": lo, "raw_hi": hi, "idx": idx,
                     "pool": scoring.effective_pool(heroes), "tot": tot})
    scoring.score_all(rows)
    by_pid = {r["pid"]: r for r in rows}

    out = {}
    wanted = set(player_ids) if player_ids else None
    for pid, (p, accts, heroes) in gathered.items():
        if wanted is not None and pid not in wanted:
            continue
        r = by_pid[pid]
        tot = r["tot"]
        m = tot["m"]
        mins = tot["t"] / 60.0
        hero_list = []
        for hid, h in heroes.items():
            if h["m"] <= 0:
                continue
            hlo, hhi = stats_mod.wilson(h["w"], h["m"])
            hm = scoring.hero_metrics(h)
            b = base.get(hid) or {}
            hero_list.append({
                "hero_id": hid, "name": names.get(hid, f"#{hid}"), "matches": h["m"], "wins": h["w"],
                "winrate": h["w"] / h["m"], "wr_lo": hlo, "wr_hi": hhi,
                "wr_adj": stats_mod.shrink_rate(h["w"], h["m"], hero_prior.get(hid, 0.5), HERO_PRIOR_N),
                "kills": h["k"], "deaths": h["d"], "assists": h["a"],
                "kd": h["k"] / max(h["d"], 1), "kda": hm["kda"],
                "idx_kda": stats_mod.shrink_ratio(hm["kda"] / b["kda"], h["m"], 1.0, 15) if b.get("kda") else None,
                "damage_per_match": h["dmg"] / h["m"], "dmg_per_min": hm["dmg"], "nw_per_min": hm["nw"],
                "time_played_s": h["t"], "last_played": h["last"],
                "reliability": stats_mod.reliability(h["m"]),
            })
        hero_list.sort(key=lambda x: -x["matches"])
        weights = {h["hero_id"]: (heroes[h["hero_id"]]["t"] or h["matches"]) for h in hero_list}
        if m >= ROLE_MIN_MATCHES:
            main_roles, breakdown = roles_mod.player_roles(weights, roles_by_hero, threshold)
            role_text = roles_mod.breakdown_text(breakdown)
        else:
            main_roles, breakdown, role_text = [], [], "insufficient sample"
        named = [(rl, v) for rl, v in breakdown if rl != "No role"]
        manual = con.execute("SELECT * FROM manual WHERE player_id=?", (pid,)).fetchone()
        team, team_src = teams.get(pid, (None, None))
        pr = ranks.get(pid, {})
        prim = steam.get(p["primary_account_id"]) or {}
        steam_name = prim.get("personaname") or next((a["steam_name"] for a in accts if a["steam_name"]), None)
        name = p["display_name"] or steam_name or str(p["primary_account_id"])
        b_best = max((badges[a["account_id"]] for a in accts if a["account_id"] in badges and badges[a["account_id"]][0]),
                     key=lambda x: x[0] or 0, default=None)
        badge = b_best[0] if b_best else max((a["badge"] or 0 for a in accts), default=0) or None
        m7, w7 = (sum(stats7.get(a["account_id"], (0, 0))[0] for a in accts), sum(stats7.get(a["account_id"], (0, 0))[1] for a in accts))
        wr_adj7 = stats_mod.shrink_rate(w7, m7, prior_m, prior_n) if m7 else None
        out[pid] = {
            "id": pid,
            "name": name,
            "steam_name": steam_name,
            "avatar": images.steam_avatar_path(prim.get("avatar")),
            "primary_account_id": p["primary_account_id"],
            "accounts": accts,
            "team": team,
            "team_source": team_src,
            "rank": pr.get(current_lid) if current_lid is not None else None,
            "ranks": {str(k): v for k, v in pr.items()},
            "badge": badge,
            "flat_progress": b_best[1] if b_best else None,
            "first_in_current": first_in_current.get(pid),
            "history_start": hist_start,
            "window": window,
            "stats": {
                "matches": m, "wins": tot["w"], "winrate": (tot["w"] / m) if m else None,
                "wr_lo": r["raw_lo"] if m else None, "wr_hi": r["raw_hi"] if m else None,
                "wr_adj": r["wr_adj"] if m else None,
                "confidence": m / (m + prior_n),
                "kills": tot["k"], "deaths": tot["d"], "assists": tot["a"],
                "kd": (tot["k"] / max(tot["d"], 1)) if m else None,
                "kda": ((tot["k"] + tot["a"]) / max(tot["d"], 1)) if m else None,
                "damage_per_match": (tot["dmg"] / m) if m else None,
                "dmg_per_min": (tot["dmg"] / mins) if mins else None,
                "nw_per_min": (tot["nwm"] / mins) if mins else None,
                "obj_damage_per_min": (tot["objm"] / mins) if mins else None,
                "time_played_s": tot["t"],
                "idx_kda": r["idx_adj"]["kda"], "idx_dmg": r["idx_adj"]["dmg"],
                "idx_nw": r["idx_adj"]["nw"], "idx_obj": r["idx_adj"]["obj"],
                "pool": r["pool"],
                "matches_7d": m7, "wins_7d": w7,
                "form": (wr_adj7 - r["wr_adj"]) if (m7 and m) else None,
                "active": m7 > 0,
            },
            "score_parts": r["score_parts"],
            "score_default": r["score_default"],
            "score_lo": r["score_lo"],
            "score_hi": r["score_hi"],
            "score_win_band": [r.get("parts_lo_win"), r.get("parts_hi_win")] if r["score_parts"] else None,
            "provisional": r["provisional"],
            "heroes": hero_list,
            "top_hero_share": (hero_list[0]["matches"] / m) if m and hero_list else None,
            "roles": main_roles,
            "role_breakdown": [[rl, round(v, 4)] for rl, v in breakdown],
            "role_text": role_text,
            "role_primary": named[0][0] if named else None,
            "role_secondary": named[1][0] if len(named) > 1 and named[1][1] >= threshold else None,
            "reliability": stats_mod.reliability(m),
            "prior": {"mean": prior_m, "n": prior_n},
            "manual": {
                "twitter": manual["twitter"] if manual else None,
                "twitch": manual["twitch"] if manual else None,
                "discord": manual["discord"] if manual else None,
                "adult": manual["adult"] if manual else "desconocido",
                "status": manual["status"] if manual else "pendiente",
                "notes": manual["notes"] if manual else None,
                "team": manual["team"] if manual else None,
            },
        }
    return out


def materialize(con, player_ids=None):
    data = build_all(con, player_ids)
    with con:
        if not player_ids:
            con.execute("DELETE FROM summaries")
        for pid, s in data.items():
            con.execute("INSERT OR REPLACE INTO summaries(player_id, data) VALUES(?,?)", (pid, json.dumps(s, ensure_ascii=False)))
    invalidate()
    return len(data)


def invalidate():
    with _cache_lock:
        _cache["version"] += 1
        _cache["body"] = None


def all_json(con):
    """Cuerpo JSON (bytes) con todos los resúmenes; se cachea hasta la siguiente invalidación."""
    with _cache_lock:
        if _cache["body"] is not None:
            return _cache["body"]
    rows = [r[0] for r in con.execute("SELECT data FROM summaries ORDER BY player_id")]
    body = ("[" + ",".join(rows) + "]").encode("utf-8")
    with _cache_lock:
        _cache["body"] = body
    return body


def get_one(con, pid):
    r = con.execute("SELECT data FROM summaries WHERE player_id=?", (pid,)).fetchone()
    return json.loads(r[0]) if r else None
