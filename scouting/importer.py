"""Importación (best-effort) de un scouting.db de la versión anterior.

No se conoce su esquema exacto, así que se inspecciona: se buscan tablas con una columna de cuenta
(account_id / steam_id / id) y columnas de campos manuales (twitter, twitch, discord, estado/status,
notas/notes, equipo/team, mayor de edad), y tablas de snapshots (rank + cuenta + fecha).
Nunca se importa una edad exacta."""
import pathlib
import sqlite3

from . import players, summary
from .db import now
from .ids import to_account_id

ACCOUNT_COLS = ["account_id", "accountid", "steam_id", "steamid", "steamid3", "player_account_id", "id"]
FIELD_ALIASES = {
    "twitter": ["twitter", "x", "twitter_x"],
    "twitch": ["twitch"],
    "discord": ["discord"],
    "status": ["status", "estado"],
    "notes": ["notes", "notas", "nota", "note"],
    "team": ["team", "equipo"],
    "adult": ["adult", "mayor_edad", "mayor_de_edad", "is_adult", "adulto"],
}
STATUS_MAP = {s.replace(" ", ""): s for s in players.STATUSES}


def _ro_uri(path):
    return pathlib.Path(path).resolve().as_uri() + "?mode=ro"


def _cols(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def inspect(path):
    src = sqlite3.connect(_ro_uri(path), uri=True)
    tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    out = {}
    for t in tables:
        cols = [c.lower() for c in _cols(src, t)]
        n = src.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        out[t] = {"columns": cols, "rows": n}
    src.close()
    return out


def _adult(v):
    s = str(v or "").strip().lower()
    if s in ("1", "true", "si", "sí", "yes", "y"):
        return "sí"
    if s in ("0", "false", "no", "n"):
        return "no"
    return "desconocido"


def import_db(con, path, dry_run=False):
    src = sqlite3.connect(_ro_uri(path), uri=True)
    src.row_factory = sqlite3.Row
    report = {"manual": 0, "snapshots": 0, "entries": 0, "tables": {}, "skipped": []}
    tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    touched = set()
    for t in tables:
        cols = {c.lower(): c for c in _cols(src, t)}
        acol = next((cols[c] for c in ACCOUNT_COLS if c in cols), None)
        fmap = {f: cols[a] for f, al in FIELD_ALIASES.items() for a in al if a in cols}
        manual_fields = {f for f in fmap if f in ("twitter", "twitch", "discord", "notes", "status")}
        if acol and manual_fields:
            n = 0
            for r in src.execute(f'SELECT * FROM "{t}"'):
                aid = to_account_id(r[acol])
                if not aid:
                    continue
                vals = {}
                for f, c in fmap.items():
                    v = r[c]
                    if v is None or str(v).strip() == "":
                        continue
                    if f == "adult":
                        v = _adult(v)
                    elif f == "status":
                        v = STATUS_MAP.get(str(v).strip().lower().replace(" ", ""), None)
                        if not v:
                            continue
                    else:
                        v = str(v)
                    vals[f] = v
                if not vals:
                    continue
                n += 1
                if dry_run:
                    continue
                pid = players.player_of(con, aid)
                with con:
                    if pid is None:
                        pid = players.create_player(con, aid, None, "manual")
                    con.execute("INSERT OR IGNORE INTO manual(player_id) VALUES(?)", (pid,))
                    cur = con.execute("SELECT * FROM manual WHERE player_id=?", (pid,)).fetchone()
                    for f, v in vals.items():
                        # no pisar lo que ya se haya rellenado en esta versión
                        if f in ("adult",) and cur["adult"] != "desconocido":
                            continue
                        if f == "status" and cur["status"] != "pendiente":
                            continue
                        if f not in ("adult", "status") and cur[f]:
                            continue
                        con.execute(f"UPDATE manual SET {f}=?, updated_at=? WHERE player_id=?", (v, now(), pid))
                touched.add(pid)
            report["manual"] += n
            report["tables"][t] = f"campos manuales ({n} filas con datos)"
        rank_col = cols.get("rank")
        time_col = next((cols[c] for c in ("taken_at", "snapshot_at", "fetched_at", "timestamp", "ts", "date", "created_at") if c in cols), None)
        if acol and rank_col and time_col:
            groups = {}
            for r in src.execute(f'SELECT "{acol}" a, "{rank_col}" r, "{time_col}" t FROM "{t}"'):
                ts = r["t"]
                if isinstance(ts, str):
                    import datetime
                    try:
                        ts = int(datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
                    except ValueError:
                        continue
                aid = to_account_id(r["a"])
                if aid and r["r"] is not None and ts:
                    groups.setdefault(int(ts), []).append((int(r["r"]), aid))
            report["tables"][t] = f"snapshots ({len(groups)})"
            if dry_run:
                report["snapshots"] += len(groups)
                continue
            import json as _json
            from .db import kv_get
            intervals = _json.loads(kv_get(con, "season_intervals") or "[]")
            for ts, entries in sorted(groups.items()):
                # cada snapshot se asigna a la temporada cuyo intervalo contiene su fecha
                lid = next((i[2] for i in intervals if i[0] <= ts < i[1]), None)
                with con:
                    sid = con.execute("INSERT INTO lb_snapshots(leaderboard_id, region, season, taken_at, n_entries) VALUES(?,?,?,?,?)",
                                      (lid, "importado", "importado", ts, len(entries))).lastrowid
                    for rank, aid in entries:
                        con.execute("INSERT INTO lb_entries(snapshot_id, rank, account_id, player_id) VALUES(?,?,?,?)", (sid, rank, aid, players.player_of(con, aid)))
                report["snapshots"] += 1
                report["entries"] += len(entries)
        if t not in report["tables"]:
            report["skipped"].append(t)
    src.close()
    if touched and not dry_run:
        summary.materialize(con)
    return report
