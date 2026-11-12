"""Actualización en segundo plano: leaderboard -> cuentas -> equipos -> stats -> nombres -> resúmenes.

Cada paso es idempotente; si el proceso se corta, el trabajo «running» se reanuda al arrancar
con la misma marca de tiempo y se saltan las cuentas ya descargadas en esa ejecución."""
import hashlib
import json
import threading
import time
import traceback

from . import api as api_mod
from . import config, db, players, summary, teams
from .db import kv_get, kv_set, now

STEPS = ["leaderboard", "teams", "stats", "names", "materialize"]
STEP_LABELS = {
    "leaderboard": "Descargando leaderboard",
    "teams": "Leyendo equipos.txt",
    "stats": "Descargando stats por héroe",
    "names": "Nombres de Steam",
    "materialize": "Calculando resúmenes",
}


class Updater:
    def __init__(self, client, db_path=None):
        self.client = client
        self.db_path = db_path
        self._badges = {}
        self._thread = None
        self._lock = threading.Lock()
        self.status = {"running": False, "step": None, "label": None, "done": 0, "total": 0, "message": "", "error": None}

    # ----------------------------------------------------------- control
    def con(self):
        return db.get(self.db_path)

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, reason="manual"):
        with self._lock:
            if self.is_running():
                return False
            self._thread = threading.Thread(target=self._run_safe, args=(reason,), daemon=True, name="updater")
            self._thread.start()
            return True

    def scheduler(self, stop_event):
        """Bucle: reanuda trabajos interrumpidos y lanza la actualización cada N horas."""
        con = self.con()
        with con:
            con.execute("UPDATE jobs SET state='interrupted' WHERE state='running'")
        while not stop_event.is_set():
            try:
                cfg = config.load()
                last = int(kv_get(con, "last_success", 0) or 0)
                interrupted = con.execute("SELECT id FROM jobs WHERE kind='update' AND state='interrupted' ORDER BY id DESC LIMIT 1").fetchone()
                due = time.time() - last >= float(cfg["update_interval_hours"]) * 3600
                if not self.is_running() and (interrupted or due):
                    self.start("reanudación" if interrupted else "programada")
            except Exception as e:  # el planificador no debe morir
                print(f"[actualizador] error en el planificador: {e}")
            stop_event.wait(60)

    def snapshot(self):
        con = self.con()
        s = dict(self.status)
        s["running"] = self.is_running()
        s["last_success"] = int(kv_get(con, "last_success", 0) or 0) or None
        cfg = config.load()
        if s["last_success"]:
            s["next_run"] = s["last_success"] + int(float(cfg["update_interval_hours"]) * 3600)
        last = con.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 1").fetchone()
        s["last_job"] = dict(last) if last else None
        return s

    def _set(self, **kw):
        self.status.update(kw)

    # ------------------------------------------------------------- run
    def _run_safe(self, reason):
        con = self.con()
        job = con.execute("SELECT * FROM jobs WHERE kind='update' AND state='interrupted' ORDER BY id DESC LIMIT 1").fetchone()
        if job:
            job_id, started = job["id"], job["started_at"]
            start_step = job["step"] if job["step"] in STEPS else STEPS[0]
            with con:
                con.execute("UPDATE jobs SET state='running', message=? WHERE id=?", (f"reanudado ({reason})", job_id))
                con.execute("UPDATE jobs SET state='superseded' WHERE kind='update' AND state='interrupted' AND id<>?", (job_id,))
            print(f"[actualizador] Reanudando la actualización #{job_id} desde el paso «{start_step}».")
        else:
            started = now()
            with con:
                job_id = con.execute(
                    "INSERT INTO jobs(kind,state,step,started_at,message) VALUES('update','running',?,?,?)", (STEPS[0], started, reason)
                ).lastrowid
            start_step = STEPS[0]
            print(f"[actualizador] Actualización #{job_id} iniciada ({reason}).")
        self._set(running=True, error=None, message="", done=0, total=0)
        try:
            for step in STEPS[STEPS.index(start_step):]:
                with con:
                    con.execute("UPDATE jobs SET step=? WHERE id=?", (step, job_id))
                self._set(step=step, label=STEP_LABELS[step], done=0, total=0, message="")
                getattr(self, "step_" + step)(con, started)
            with con:
                con.execute("UPDATE jobs SET state='done', finished_at=? WHERE id=?", (now(), job_id))
                kv_set(con, "last_success", now())
            self._set(step=None, label="Completado", message="Actualización completada")
            print(f"[actualizador] Actualización #{job_id} completada.")
        except Exception as e:
            traceback.print_exc()
            msg = f"{type(e).__name__}: {e}"
            with con:
                con.execute("UPDATE jobs SET state='interrupted', message=? WHERE id=?", (msg, job_id))
            self._set(error=msg, label="Error (se reanudará)")
            print(f"[actualizador] Error: {msg}. Se reanudará en el próximo ciclo.")

    # ------------------------------------------------------------ pasos
    def step_leaderboard(self, con, started):
        cfg = config.load()
        region = cfg["region"]
        seasons = self.client.ranked_seasons()
        cur_lid, _ = api_mod.current_leaderboard_id(seasons)
        names = api_mod.season_names(seasons)
        with con:
            kv_set(con, "current_leaderboard_id", cur_lid if cur_lid is not None else "")
            kv_set(con, "region", region)
            kv_set(con, "season_names", json.dumps({str(k): v for k, v in names.items()}))
            kv_set(con, "season_intervals", json.dumps([[iv.get("start_timestamp", 0), iv.get("end_timestamp", 1 << 62), iv["leaderboard_id"]]
                                                       for s in seasons for iv in s.get("intervals", []) if iv.get("leaderboard_id") is not None]))
        # nombres de héroes (para roles y vistas)
        heroes = self.client.heroes()
        hn = {h["id"]: h["name"] for h in heroes if h.get("player_selectable") and not h.get("disabled")}
        with con:
            kv_set(con, "hero_names", json.dumps(hn))
            kv_set(con, "hero_images", json.dumps({h["id"]: (h.get("images") or {}).get("icon_image_small_webp") for h in heroes if h["id"] in hn}))

        lids = [cur_lid] + [int(x) for x in cfg.get("extra_leaderboard_ids") or [] if int(x) != cur_lid]
        for i, lid in enumerate(lids):
            self._set(message=f"{region} · {names.get(lid, lid)}", done=i, total=len(lids))
            already = con.execute("SELECT 1 FROM lb_snapshots WHERE leaderboard_id IS ? AND region=? AND taken_at>=?", (lid, region, started)).fetchone()
            if already:
                continue
            entries = self.client.leaderboard(region, lid)
            digest = hashlib.sha1(json.dumps([(e.get("rank"), e.get("account_name"), e.get("possible_account_ids")) for e in entries]).encode()).hexdigest()
            if lid != cur_lid and kv_get(con, f"lb_digest_{region}_{lid}") == digest:
                continue  # temporada cerrada sin cambios: no hace falta otro snapshot
            resolved = self.resolve_accounts(con, entries)
            with con:
                sid = con.execute(
                    "INSERT INTO lb_snapshots(leaderboard_id, region, season, taken_at, n_entries) VALUES(?,?,?,?,?)",
                    (lid, region, names.get(lid), started, len(entries)),
                ).lastrowid
                for e in entries:
                    aid = resolved.get(_key(e))
                    pid = None
                    if aid:
                        pid = players.player_of(con, aid)
                        if pid is None:
                            pid = players.create_player(con, aid, e.get("account_name"), "leaderboard", 1)
                        else:
                            con.execute("UPDATE players SET display_name=?, in_leaderboard=1 WHERE id=? AND primary_account_id=?", (e.get("account_name"), pid, aid))
                    con.execute(
                        "INSERT INTO lb_entries(snapshot_id, rank, account_name, account_id, player_id, top_hero_ids) VALUES(?,?,?,?,?,?)",
                        (sid, e.get("rank"), e.get("account_name"), aid, pid, json.dumps(e.get("top_hero_ids") or [])),
                    )
                for a, b in self._badges.items():
                    con.execute("UPDATE accounts SET badge=? WHERE account_id=?", (b, a))
                self._badges = {}
                kv_set(con, f"lb_digest_{region}_{lid}", digest)
            print(f"[actualizador] Leaderboard {region} {names.get(lid, lid)}: {len(entries)} entradas.")

    def resolve_accounts(self, con, entries):
        """Elige la cuenta de cada entrada entre possible_account_ids.

        Regla (verificada en vivo): el badge más alto de /v1/players/rank; en empate, la cuenta cuyo
        nombre de Steam coincide con el de la leaderboard y, después, la de más partidas en 30 días."""
        out, pending = {}, []
        for e in entries:
            k = _key(e)
            r = con.execute("SELECT account_id FROM lb_resolution WHERE name=? AND candidates=?", k).fetchone()
            if r:
                out[k] = r[0]
            elif len(e.get("possible_account_ids") or []) == 1:
                out[k] = e["possible_account_ids"][0]
                with con:
                    con.execute("INSERT OR REPLACE INTO lb_resolution VALUES(?,?,?,?,?,?)", (*k, out[k], "única", 1, now()))
            elif e.get("possible_account_ids"):
                pending.append(e)
            else:
                out[k] = None
        self._badges = {}
        if not pending:
            return out
        # por tramos de ~1000 candidatas: cada tramo se guarda (si se corta, no se repite)
        total = sum(len(e["possible_account_ids"]) for e in pending)
        done, chunk, size = 0, [], 0
        for e in pending + [None]:
            if e is not None:
                chunk.append(e)
                size += len(e["possible_account_ids"])
            if chunk and (e is None or size >= 1000):
                self._set(message=f"Resolviendo cuentas ({done}/{total} candidatas)")
                out.update(self._resolve_chunk(con, chunk))
                done += size
                chunk, size = [], 0
        return out

    def _resolve_chunk(self, con, pending):
        out = {}
        cands = sorted({a for e in pending for a in e["possible_account_ids"]})
        badges = {}
        for i in range(0, len(cands), 1000):
            for r in self.client.ranks(cands[i:i + 1000]):
                badges[r["account_id"]] = r.get("badge") or 0
        ties = {}
        for e in pending:
            ids = e["possible_account_ids"]
            top = max(badges.get(a, 0) for a in ids)
            best = [a for a in ids if badges.get(a, 0) == top]
            ties[_key(e)] = (e, best, top)
        need_steam = sorted({a for e, best, _ in ties.values() if len(best) > 1 for a in best})
        steam = {}
        for i in range(0, len(need_steam), 100):
            for s in self.client.steam(need_steam[i:i + 100]):
                steam[s["account_id"]] = (s.get("personaname"), s.get("matches_played_last_30d") or 0)
        with con:
            for k, (e, best, top) in ties.items():
                if len(best) == 1:
                    aid, method = best[0], f"badge {top}"
                else:
                    name = e.get("account_name") or ""
                    best.sort(key=lambda a: (steam.get(a, ("", 0))[0] == name, steam.get(a, ("", 0))[1]), reverse=True)
                    aid, method = best[0], f"empate badge {top}: nombre Steam + partidas 30d"
                out[k] = aid
                con.execute("INSERT OR REPLACE INTO lb_resolution VALUES(?,?,?,?,?,?)", (*k, aid, method, len(e["possible_account_ids"]), now()))
        self._badges.update({a: badges.get(a) for a in out.values() if a in badges})
        return out

    def step_teams(self, con, started):
        sync_teams(con)

    def step_stats(self, con, started):
        cfg = config.load()
        min_ts = started - int(cfg["stats_days"]) * 86400
        all_ids = [r[0] for r in con.execute("SELECT account_id FROM accounts ORDER BY account_id")]
        done = {r[0] for r in con.execute("SELECT account_id FROM stats_fetched WHERE fetched_at>=?", (started,))}
        todo = [a for a in all_ids if a not in done]
        n = int(cfg.get("batch_size") or 50)
        total = len(all_ids)
        self._set(total=total, done=total - len(todo))
        for i in range(0, len(todo), n):
            batch = todo[i:i + n]
            rows = self.client.hero_stats(batch, min_ts)
            with con:
                con.execute("DELETE FROM hero_stats WHERE account_id IN (%s)" % ",".join("?" * len(batch)), batch)
                for r in rows:
                    con.execute(
                        "INSERT OR REPLACE INTO hero_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (r["account_id"], r["hero_id"], r.get("matches_played"), r.get("wins"), r.get("kills"), r.get("deaths"),
                         r.get("assists"), r.get("total_player_damage"), r.get("total_player_damage_taken"), r.get("total_boss_damage"),
                         r.get("total_creep_damage"), r.get("obj_damage_per_min"), r.get("damage_per_min"), r.get("networth_per_min"),
                         r.get("accuracy"), r.get("time_played"), r.get("last_played")),
                    )
                con.executemany("INSERT OR REPLACE INTO stats_fetched VALUES(?,?)", [(a, started) for a in batch])
            self._set(done=total - len(todo) + i + len(batch), message=f"{total - len(todo) + i + len(batch)}/{total} cuentas")

    def step_names(self, con, started):
        ids = [r[0] for r in con.execute(
            "SELECT a.account_id FROM accounts a JOIN players p ON p.id=a.player_id "
            "WHERE a.steam_name IS NULL AND (a.steam_checked IS NULL OR a.steam_checked < ?) "
            "AND (p.display_name IS NULL OR a.source<>'leaderboard')", (started - 7 * 86400,))]
        self._set(total=len(ids), done=0)
        for i in range(0, len(ids), 100):
            batch = ids[i:i + 100]
            got = {s["account_id"]: s.get("personaname") for s in self.client.steam(batch)}
            with con:
                for a in batch:
                    con.execute("UPDATE accounts SET steam_name=?, steam_checked=? WHERE account_id=?", (got.get(a), now(), a))
            self._set(done=i + len(batch))

    def step_materialize(self, con, started):
        n = summary.materialize(con)
        # historial para tendencias (una fila por jugador y actualización)
        with con:
            for r in con.execute("SELECT data FROM summaries").fetchall():
                s = json.loads(r[0])
                st = s["stats"]
                con.execute(
                    "INSERT OR REPLACE INTO stats_history VALUES(?,?,?,?,?,?,?,?)",
                    (s["id"], started, st["matches"], st["wins"], st["kills"], st["deaths"], st["assists"], s.get("rank")),
                )
        self._set(done=n, total=n)


def _key(e):
    return (e.get("account_name") or "", ",".join(str(a) for a in sorted(e.get("possible_account_ids") or [])))


def sync_teams(con, path=None):
    """Carga equipos.txt: plantillas, cuentas del mismo jugador (misma línea) y jugadores fuera de la leaderboard."""
    rows, errors = teams.read_file(path or config.TEAMS_PATH)
    with con:
        con.execute("DELETE FROM team_rosters")
        for line_no, (ids, team) in enumerate(rows, 1):
            pids = [p for p in (players.player_of(con, a) for a in ids) if p is not None]
            if pids:
                target = min(pids, key=lambda p: (0 if con.execute("SELECT in_leaderboard FROM players WHERE id=?", (p,)).fetchone()[0] else 1, p))
                for p in set(pids) - {target}:
                    players.merge(con, target, p)
            else:
                target = players.create_player(con, ids[0], None, "team")
            for a in ids:
                if players.player_of(con, a) is None:
                    con.execute("INSERT INTO accounts(account_id, player_id, source) VALUES(?,?,?)", (a, target, "team"))
                con.execute("INSERT OR IGNORE INTO team_rosters(team, account_id, line_no) VALUES(?,?,?)", (team, a, line_no))
    for e in errors:
        print(f"[equipos.txt] {e}")
    return {"lines": len(rows), "errors": errors}
