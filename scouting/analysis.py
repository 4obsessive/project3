"""Consultas de scouting que no son por jugador: climbers y partidas recientes de un equipo."""
import threading
import time
from collections import defaultdict

from .db import kv_get

_hist_cache = {}
_hist_lock = threading.Lock()


def current_lid(con):
    v = kv_get(con, "current_leaderboard_id")
    return int(v) if v else None


def climbers(con, days):
    lid = current_lid(con)
    snaps = con.execute("SELECT id, taken_at FROM lb_snapshots WHERE leaderboard_id IS ? ORDER BY taken_at", (lid,)).fetchall()
    out = {"days": days, "leaderboard_id": lid, "snapshots": len(snaps), "climbers": [], "new": [], "warning": None}
    if len(snaps) < 2:
        out["warning"] = ("Aún no hay historial suficiente: la API no da el ranking pasado, así que se acumula desde la primera "
                          "descarga. Vuelve cuando haya al menos dos snapshots separados en el tiempo.")
        return out
    latest = snaps[-1]
    target = latest["taken_at"] - days * 86400
    older = [s for s in snaps[:-1] if s["taken_at"] <= target + 3600]
    if older:
        base = older[-1]
    else:
        base = snaps[0]
        have = (latest["taken_at"] - base["taken_at"]) / 86400
        out["warning"] = f"Solo hay {have:.1f} días de historial (primer snapshot). Se compara con ese en lugar de con hace {days} días."
    out["base_taken_at"], out["latest_taken_at"] = base["taken_at"], latest["taken_at"]

    def ranks(sid):
        return {r[0]: r[1] for r in con.execute("SELECT player_id, MIN(rank) FROM lb_entries WHERE snapshot_id=? AND player_id IS NOT NULL GROUP BY player_id", (sid,))}

    old, new = ranks(base["id"]), ranks(latest["id"])
    names = {r[0]: r[1] for r in con.execute("SELECT id, display_name FROM players")}
    for pid, r in new.items():
        if pid in old:
            if old[pid] > r:
                out["climbers"].append({"player_id": pid, "name": names.get(pid), "from": old[pid], "to": r, "delta": old[pid] - r})
        else:
            out["new"].append({"player_id": pid, "name": names.get(pid), "rank": r})
    out["climbers"].sort(key=lambda x: -x["delta"])
    out["new"].sort(key=lambda x: x["rank"])
    return out


def roster(con, team, extra=()):
    """Cuentas de la plantilla: equipos.txt + jugadores con ese equipo en el campo manual + extra."""
    ids = {r[0] for r in con.execute("SELECT account_id FROM team_rosters WHERE team=?", (team,))}
    ids |= {r[0] for r in con.execute("SELECT a.account_id FROM accounts a JOIN manual m ON m.player_id=a.player_id WHERE TRIM(m.team)=?", (team,))}
    # todas las cuentas enlazadas de esos jugadores
    if ids:
        pids = {r[0] for r in con.execute("SELECT DISTINCT player_id FROM accounts WHERE account_id IN (%s)" % ",".join("?" * len(ids)), tuple(ids))}
        if pids:
            ids |= {r[0] for r in con.execute("SELECT account_id FROM accounts WHERE player_id IN (%s)" % ",".join("?" * len(pids)), tuple(pids))}
    return ids | {int(a) for a in extra}


def teams_overview(con):
    teams = defaultdict(lambda: {"players": {}, "accounts": []})
    for r in con.execute(
        "SELECT tr.team, tr.account_id, a.player_id, p.display_name, a.steam_name FROM team_rosters tr "
        "LEFT JOIN accounts a ON a.account_id=tr.account_id LEFT JOIN players p ON p.id=a.player_id ORDER BY tr.team, tr.line_no"
    ):
        t = teams[r["team"]]
        t["accounts"].append(r["account_id"])
        if r["player_id"]:
            t["players"][r["player_id"]] = r["display_name"] or r["steam_name"] or str(r["account_id"])
    for r in con.execute("SELECT m.team, p.id, p.display_name FROM manual m JOIN players p ON p.id=m.player_id WHERE m.team IS NOT NULL AND TRIM(m.team)<>''"):
        teams[r["team"].strip()]["players"].setdefault(r["id"], r["display_name"])
    return [{"team": k, "players": [{"id": pid, "name": n} for pid, n in v["players"].items()], "accounts": v["accounts"]} for k, v in sorted(teams.items())]


def recent_team_matches(con, client, team, extra=(), min_players=3, days=60):
    """Partidas recientes en las que al menos `min_players` cuentas de la plantilla jugaron en el mismo equipo."""
    ids = sorted(roster(con, team, extra))
    min_ts = time.time() - days * 86400
    found = defaultdict(lambda: defaultdict(set))
    info = {}
    errors = []
    for a in ids:
        with _hist_lock:
            c = _hist_cache.get(a)
        if c and time.time() - c[0] < 600:
            hist = c[1]
        else:
            try:
                hist = client.match_history(a)
            except Exception as e:
                errors.append(f"{a}: {e}")
                continue
            with _hist_lock:
                _hist_cache[a] = (time.time(), hist)
        for h in hist:
            if (h.get("start_time") or 0) < min_ts:
                continue
            found[h["match_id"]][h.get("player_team")].add(a)
            info[h["match_id"]] = h
    stored = {r[0] for r in con.execute("SELECT match_id FROM matches")}
    out = []
    for mid, by_team in found.items():
        team_side, accts = max(by_team.items(), key=lambda kv: len(kv[1]))
        if len(accts) >= min_players:
            h = info[mid]
            out.append({"match_id": mid, "start_time": h.get("start_time"), "duration_s": h.get("match_duration_s"),
                        "side": team_side, "roster_players": len(accts), "won": h.get("match_result") == team_side,
                        "match_mode": h.get("match_mode"), "stored": mid in stored})
    out.sort(key=lambda x: -(x["start_time"] or 0))
    return {"team": team, "roster_accounts": len(ids), "matches": out, "errors": errors}
