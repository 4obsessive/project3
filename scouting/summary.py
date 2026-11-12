"""Resúmenes de jugador materializados (se recalculan tras cada actualización o edición)."""
import json
import threading

from . import roles as roles_mod
from .db import kv_get

_cache_lock = threading.Lock()
_cache = {"version": 0, "body": None}

RELIABILITY = [(25, "Alta"), (10, "Media"), (0, "Baja")]


def reliability(matches):
    for lim, label in RELIABILITY:
        if matches >= lim:
            return label
    return "Baja"


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


def build_all(con, player_ids=None):
    names = hero_names(con)
    table, threshold = roles_mod.load_table()
    roles_by_hero = roles_mod.hero_roles(table, names)
    current_lid = kv_get(con, "current_leaderboard_id")
    current_lid = int(current_lid) if current_lid else None
    teams = effective_team(con)
    latest = _latest_snapshots(con)

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

    q = "SELECT * FROM players"
    args = ()
    if player_ids:
        q += " WHERE id IN (%s)" % ",".join("?" * len(player_ids))
        args = tuple(player_ids)
    players = con.execute(q, args).fetchall()
    out = {}
    for p in players:
        pid = p["id"]
        accts = [dict(r) for r in con.execute("SELECT account_id, source, steam_name, badge FROM accounts WHERE player_id=? ORDER BY account_id=? DESC", (pid, p["primary_account_id"]))]
        ids = [a["account_id"] for a in accts]
        heroes = {}
        if ids:
            for r in con.execute("SELECT * FROM hero_stats WHERE account_id IN (%s)" % ",".join("?" * len(ids)), ids):
                h = heroes.setdefault(r["hero_id"], {"m": 0, "w": 0, "k": 0, "d": 0, "a": 0, "dmg": 0, "t": 0, "objm": 0.0, "last": 0})
                h["m"] += r["matches"] or 0
                h["w"] += r["wins"] or 0
                h["k"] += r["kills"] or 0
                h["d"] += r["deaths"] or 0
                h["a"] += r["assists"] or 0
                h["dmg"] += r["player_damage"] or 0
                h["t"] += r["time_played"] or 0
                h["objm"] += (r["obj_damage_per_min"] or 0) * (r["time_played"] or 0) / 60.0
                h["last"] = max(h["last"], r["last_played"] or 0)
        tot = {k: sum(h[k] for h in heroes.values()) for k in ("m", "w", "k", "d", "a", "dmg", "t", "objm")}
        hero_list = []
        for hid, h in heroes.items():
            if h["m"] <= 0:
                continue
            hero_list.append({
                "hero_id": hid, "name": names.get(hid, f"#{hid}"), "matches": h["m"], "wins": h["w"],
                "winrate": h["w"] / h["m"], "kills": h["k"], "deaths": h["d"], "assists": h["a"],
                "kd": h["k"] / max(h["d"], 1), "kda": (h["k"] + h["a"]) / max(h["d"], 1),
                "damage_per_match": h["dmg"] / h["m"], "last_played": h["last"],
            })
        hero_list.sort(key=lambda x: -x["matches"])
        m = tot["m"]
        main_roles, breakdown = roles_mod.player_roles({h["hero_id"]: h["matches"] for h in hero_list}, roles_by_hero, threshold)
        manual = con.execute("SELECT * FROM manual WHERE player_id=?", (pid,)).fetchone()
        team, team_src = teams.get(pid, (None, None))
        pr = ranks.get(pid, {})
        name = p["display_name"] or next((a["steam_name"] for a in accts if a["steam_name"]), None) or str(p["primary_account_id"])
        out[pid] = {
            "id": pid,
            "name": name,
            "primary_account_id": p["primary_account_id"],
            "accounts": accts,
            "team": team,
            "team_source": team_src,
            "rank": pr.get(current_lid) if current_lid is not None else None,
            "ranks": {str(k): v for k, v in pr.items()},
            "first_in_current": first_in_current.get(pid),
            "history_start": hist_start,
            "stats": {
                "matches": m, "wins": tot["w"], "winrate": (tot["w"] / m) if m else None,
                "kills": tot["k"], "deaths": tot["d"], "assists": tot["a"],
                "kd": (tot["k"] / max(tot["d"], 1)) if m else None,
                "kda": ((tot["k"] + tot["a"]) / max(tot["d"], 1)) if m else None,
                "damage_per_match": (tot["dmg"] / m) if m else None,
                "obj_damage_per_min": (tot["objm"] / (tot["t"] / 60.0)) if tot["t"] else None,
                "time_played_s": tot["t"],
            },
            "heroes": hero_list,
            "top_hero_share": (hero_list[0]["matches"] / m) if m and hero_list else None,
            "roles": main_roles,
            "role_breakdown": [[r, round(v, 4)] for r, v in breakdown],
            "role_text": roles_mod.breakdown_text(breakdown),
            "reliability": reliability(m),
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
