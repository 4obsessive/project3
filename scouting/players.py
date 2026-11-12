"""Operaciones sobre jugadores: crear, fusionar cuentas, campos manuales, perfil (tendencias y dúos)."""
import json
import time
from collections import defaultdict

from . import summary
from .db import now
from .ids import steam_profile_url

STATUSES = ["pendiente", "en seguimiento", "contactado", "en prueba", "fichado", "descartado"]
ADULT = ["sí", "no", "desconocido"]
MANUAL_FIELDS = ["twitter", "twitch", "discord", "adult", "status", "notes", "team"]


def player_of(con, account_id):
    r = con.execute("SELECT player_id FROM accounts WHERE account_id=?", (account_id,)).fetchone()
    return r[0] if r else None


def create_player(con, account_id, name, source, in_lb=0):
    cur = con.execute(
        "INSERT INTO players(display_name, primary_account_id, first_seen, in_leaderboard) VALUES(?,?,?,?)",
        (name, account_id, now(), in_lb),
    )
    pid = cur.lastrowid
    con.execute("INSERT INTO accounts(account_id, player_id, source) VALUES(?,?,?)", (account_id, pid, source))
    return pid


def merge(con, target, source):
    """Fusiona el jugador `source` dentro de `target` (cuentas, historial, campos manuales)."""
    if target == source:
        return target
    con.execute("UPDATE accounts SET player_id=? WHERE player_id=?", (target, source))
    con.execute("UPDATE lb_entries SET player_id=? WHERE player_id=?", (target, source))
    con.execute("DELETE FROM stats_history WHERE player_id=?", (source,))
    tm = con.execute("SELECT * FROM manual WHERE player_id=?", (target,)).fetchone()
    sm = con.execute("SELECT * FROM manual WHERE player_id=?", (source,)).fetchone()
    if sm and not tm:
        con.execute("UPDATE manual SET player_id=? WHERE player_id=?", (target, source))
    elif sm and tm:
        # completar huecos del destino con lo que tuviera el origen; notas se concatenan
        for f in ("twitter", "twitch", "discord", "team"):
            if not tm[f] and sm[f]:
                con.execute(f"UPDATE manual SET {f}=? WHERE player_id=?", (sm[f], target))
        if sm["notes"]:
            notes = ((tm["notes"] or "") + "\n" + sm["notes"]).strip()
            con.execute("UPDATE manual SET notes=? WHERE player_id=?", (notes, target))
        if tm["adult"] == "desconocido" and sm["adult"] != "desconocido":
            con.execute("UPDATE manual SET adult=? WHERE player_id=?", (sm["adult"], target))
        if tm["status"] == "pendiente" and sm["status"] != "pendiente":
            con.execute("UPDATE manual SET status=? WHERE player_id=?", (sm["status"], target))
        con.execute("DELETE FROM manual WHERE player_id=?", (source,))
    con.execute("DELETE FROM summaries WHERE player_id=?", (source,))
    tp = con.execute("SELECT display_name, in_leaderboard FROM players WHERE id=?", (target,)).fetchone()
    sp = con.execute("SELECT display_name, in_leaderboard, first_seen FROM players WHERE id=?", (source,)).fetchone()
    if sp:
        con.execute(
            "UPDATE players SET display_name=COALESCE(display_name, ?), in_leaderboard=MAX(in_leaderboard, ?), first_seen=MIN(first_seen, ?) WHERE id=?",
            (sp["display_name"], sp["in_leaderboard"], sp["first_seen"], target),
        )
    con.execute("DELETE FROM players WHERE id=?", (source,))
    return target


def link_account(con, player_id, account_id):
    """Enlaza una cuenta a un jugador. Si la cuenta ya era de otro jugador, se fusionan."""
    other = player_of(con, account_id)
    with con:
        if other is None:
            con.execute("INSERT INTO accounts(account_id, player_id, source) VALUES(?,?,?)", (account_id, player_id, "manual"))
        elif other != player_id:
            merge(con, player_id, other)
    summary.materialize(con, [player_id])
    return player_id


def unlink_account(con, player_id, account_id):
    """Separa una cuenta en un jugador nuevo (no se puede separar la cuenta principal)."""
    p = con.execute("SELECT primary_account_id FROM players WHERE id=?", (player_id,)).fetchone()
    if not p or p[0] == account_id:
        raise ValueError("No se puede separar la cuenta principal")
    with con:
        con.execute("DELETE FROM accounts WHERE account_id=? AND player_id=?", (account_id, player_id))
        create_player(con, account_id, None, "manual")
    new_pid = player_of(con, account_id)
    summary.materialize(con, [player_id, new_pid])
    return new_pid


def update_manual(con, player_id, fields):
    clean = {}
    for k, v in fields.items():
        if k not in MANUAL_FIELDS:
            continue
        if isinstance(v, str):
            v = v.strip()[:4000] or None
        if k == "status" and v not in STATUSES:
            raise ValueError(f"Estado no válido: {v}")
        if k == "adult" and v not in ADULT:
            raise ValueError("Mayor de edad debe ser sí / no / desconocido (nunca la edad exacta)")
        clean[k] = v
    if not con.execute("SELECT 1 FROM players WHERE id=?", (player_id,)).fetchone():
        raise KeyError(player_id)
    with con:
        con.execute("INSERT OR IGNORE INTO manual(player_id) VALUES(?)", (player_id,))
        for k, v in clean.items():
            con.execute(f"UPDATE manual SET {k}=?, updated_at=? WHERE player_id=?", (v, now(), player_id))
    summary.materialize(con, [player_id])
    return summary.get_one(con, player_id)


# ------------------------------------------------------------------ perfil
def trends(con, player_id, current_lid):
    rank_series = []
    if current_lid is not None:
        rank_series = [
            {"t": r[0], "rank": r[1]}
            for r in con.execute(
                "SELECT s.taken_at, MIN(e.rank) FROM lb_entries e JOIN lb_snapshots s ON s.id=e.snapshot_id "
                "WHERE e.player_id=? AND s.leaderboard_id=? GROUP BY s.id ORDER BY s.taken_at",
                (player_id, current_lid),
            )
        ]
    stats_series = []
    for r in con.execute("SELECT * FROM stats_history WHERE player_id=? ORDER BY taken_at", (player_id,)):
        m = r["matches"] or 0
        stats_series.append({
            "t": r["taken_at"], "matches": m,
            "winrate": (r["wins"] / m) if m else None,
            "kda": ((r["kills"] + r["assists"]) / max(r["deaths"], 1)) if m else None,
        })
    return {"rank": rank_series, "stats": stats_series}


def duos(con, client, player_id, days=30, max_age_s=12 * 3600):
    """Top dúos reales: partidas en las que ese compañero era el ÚNICO otro miembro del grupo.

    mate-stats (same_party=true) da, por compañero, la lista de partidas en grupo. Si en una
    partida solo aparece un compañero, era un dúo. El resultado por partida sale del
    historial de partidas del jugador (match-history)."""
    accts = [r[0] for r in con.execute("SELECT account_id FROM accounts WHERE player_id=? ORDER BY account_id", (player_id,))][:5]
    min_ts = int(time.time()) - days * 86400
    match_mates = defaultdict(set)
    party_totals = defaultdict(lambda: [0, 0])
    results = {}
    for aid in accts:
        cached = con.execute("SELECT fetched_at, data FROM mates_cache WHERE account_id=?", (aid,)).fetchone()
        if cached and time.time() - cached[0] < max_age_s:
            data = json.loads(cached[1])
        else:
            mates = client.mate_stats(aid, min_ts, same_party=True)
            try:
                hist = client.match_history(aid)
            except Exception:  # el historial es un extra: sin él no hay winrate de dúo
                hist = []
            data = {
                "mates": mates,
                # match_result = equipo ganador (verificado: player_team 1, match_result 0 -> outcome 2 = derrota)
                "results": {str(h["match_id"]): (1 if h.get("match_result") == h.get("player_team") else 0)
                            for h in hist if h.get("start_time", 0) >= min_ts},
            }
            with con:
                con.execute("INSERT OR REPLACE INTO mates_cache VALUES(?,?,?)", (aid, now(), json.dumps(data)))
        for m in data["mates"]:
            if m["mate_id"] in accts:
                continue
            party_totals[m["mate_id"]][0] += m["matches_played"]
            party_totals[m["mate_id"]][1] += m["wins"]
            for mid in m.get("matches") or []:
                match_mates[mid].add(m["mate_id"])
        results.update({int(k): v for k, v in data["results"].items()})
    duo = defaultdict(lambda: {"matches": 0, "wins": 0, "known": 0})
    for mid, mates in match_mates.items():
        if len(mates) == 1:
            (mate,) = mates
            d = duo[mate]
            d["matches"] += 1
            if mid in results:
                d["known"] += 1
                d["wins"] += results[mid]
    top = sorted(duo.items(), key=lambda kv: -kv[1]["matches"])[:5]
    ids = [m for m, _ in top] + [m for m, _ in sorted(party_totals.items(), key=lambda kv: -kv[1][0])[:5]]
    names = mate_names(con, client, ids)
    return {
        "days": days,
        "duos": [{
            "account_id": m, "name": names.get(m), "player_id": player_of(con, m),
            "duo_matches": d["matches"],
            "duo_winrate": (d["wins"] / d["known"]) if d["known"] else None,
            "duo_results_known": d["known"],
            "party_matches": party_totals[m][0],
        } for m, d in top],
        "party_mates": [{
            "account_id": m, "name": names.get(m), "player_id": player_of(con, m),
            "party_matches": v[0], "party_winrate": v[1] / v[0] if v[0] else None,
        } for m, v in sorted(party_totals.items(), key=lambda kv: -kv[1][0])[:5]],
        "note": "Dúo = partida en la que ese compañero era el único otro miembro del grupo. "
                "«Compañeros de grupo» incluye tríos y stacks.",
    }


def mate_names(con, client, ids):
    out = {}
    missing = []
    for a in set(ids):
        r = con.execute(
            "SELECT COALESCE(p.display_name, a.steam_name) FROM accounts a JOIN players p ON p.id=a.player_id WHERE a.account_id=?", (a,)
        ).fetchone()
        if r and r[0]:
            out[a] = r[0]
        else:
            missing.append(a)
    if missing and client is not None:
        try:
            for s in client.steam(missing[:100]):
                out[s["account_id"]] = s.get("personaname")
        except Exception:
            pass
    return out


def profile(con, client, player_id, current_lid, with_duos=True):
    s = summary.get_one(con, player_id)
    if not s:
        return None
    s["steam_url"] = steam_profile_url(s["primary_account_id"])
    for a in s["accounts"]:
        a["steam_url"] = steam_profile_url(a["account_id"])
    s["top_heroes"] = s["heroes"][:5]
    s["trends"] = trends(con, player_id, current_lid)
    if with_duos and client is not None:
        try:
            s["duos"] = duos(con, client, player_id)
        except Exception as e:
            s["duos"] = {"error": f"No se pudieron obtener los compañeros: {e}"}
    return s
