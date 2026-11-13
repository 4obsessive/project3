import json
import os
import unittest

from scouting import demo, report

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "demo_135801973.json")
LANE_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "demo_lane_135801973.json")


def cargar():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class Summarize(unittest.TestCase):
    def setUp(self):
        self.data = cargar()
        self.results = self.data["results"]
        self.s = demo.summarize(self.results)

    def test_queries_match_fixture(self):
        # Las 3 consultas originales siguen idénticas; la de líneas se comprueba contra su propio fixture.
        self.assertEqual({k: v for k, v in demo.QUERIES.items() if k != "lane_damage"}, self.data["queries"])
        with open(LANE_FIXTURE, encoding="utf-8") as f:
            lane = json.load(f)
        # El fixture se consultó con el límite antiguo (48000); la consulta actual solo cambia ese número.
        self.assertEqual(demo.LANE_TICK_LIMIT, (600 + 3600) * 64)
        self.assertEqual(demo.LANE_TICK_LIMIT_LEGACY, 48000)
        self.assertEqual(demo.QUERIES["lane_damage"], lane["query"].replace("d.tick < 48000", f"d.tick < {demo.LANE_TICK_LIMIT}"))

    def test_tick_to_game_seconds(self):
        rules = self.results["rules"]
        self.assertEqual(round(demo.game_seconds_from_tick(78311, rules)), 1198)
        self.assertEqual(round(demo.game_seconds_from_tick(106774, rules)), 1643)

    def test_midboss(self):
        mb = self.s["midboss"]
        self.assertEqual(len(mb), 2)
        a, b = mb
        self.assertEqual(a["damage"], {"0": 0, "1": 15731})
        self.assertEqual(a["initiator"], 1)
        self.assertEqual(a["killer"], 1)
        self.assertIs(a["stolen"], False)
        self.assertEqual(a["rejuv"], {"0": 0, "1": 3})
        self.assertEqual(round(a["t"]), 1198)
        self.assertEqual(b["rejuv"], {"0": 0, "1": 3})
        self.assertEqual(b["damage"]["1"], 22027)

    def test_koth(self):
        k = self.s["koth"]
        self.assertEqual(len(k), 3)
        self.assertEqual([x["completed_by"] for x in k], [1, 0, 0])
        self.assertEqual(round(k[0]["start_t"]), 740)
        self.assertEqual(round(k[0]["completed_t"]), 758)
        # Los curtime koth_* ya excluyen el tiempo pausado (1626 ticks antes del #2): no se restan otra vez.
        self.assertEqual((k[1]["start_t"], k[1]["completed_t"]), (round(1184.875 - 47.5625), round(1206.0625 - 47.5625)))
        self.assertEqual((k[1]["start_t"], k[1]["completed_t"]), (1137, 1158))
        self.assertEqual((k[2]["start_t"], k[2]["completed_t"]), (1596, 1603))

    def test_curtime_ignores_paused_ticks(self):
        rules = [{"tick": 0, "paused_ticks": 1626, "game_start": 47.5625}]
        self.assertEqual(demo.game_seconds_from_curtime(1184.875, 10, rules), 1184.875 - 47.5625)

    def test_koth_not_completed(self):
        inf = 3.4028235e38
        base = {"koth_team": -1, "koth_scoring": 0.0, "paused_ticks": 0, "game_start": 0.0}
        rules = [
            dict(base, tick=0, koth_start=0.0, koth_give_up=0.0),
            dict(base, tick=100, koth_start=900.0, koth_give_up=inf),
            dict(base, tick=110, koth_start=900.0, koth_give_up=960.0),
            dict(base, tick=200, koth_start=0.0, koth_give_up=0.0),
        ]
        s = demo.summarize({"rejuv": [], "rules": rules, "midboss": []})
        self.assertEqual(len(s["koth"]), 1)
        self.assertIsNone(s["koth"][0]["completed_by"])
        self.assertIsNone(s["koth"][0]["completed_t"])

    def test_midboss_t_first(self):
        rules = self.results["rules"]
        a, b = self.s["midboss"]
        self.assertEqual(a["t_first"], round(demo.game_seconds_from_tick(77467, rules)))
        self.assertEqual(b["t_first"], round(demo.game_seconds_from_tick(106044, rules)))

    def test_midboss_t_first_none_for_rejuv_only(self):
        rules = [{"tick": 0, "koth_team": 0, "koth_scoring": 0.0, "koth_start": 0.0,
                  "koth_give_up": 0.0, "paused_ticks": 0, "game_start": 0.0}]
        s = demo.summarize({"rules": rules, "midboss": [],
                            "rejuv": [{"tick": 6400, "killing_team": 2, "user_team": 2}]})
        self.assertIsNone(s["midboss"][0]["t_first"])

    def test_koth_end_t_completed(self):
        for x in self.s["koth"]:
            self.assertEqual(x["end_t"], x["completed_t"])

    def test_koth_end_t_abandoned(self):
        inf = 3.4028235e38
        base = {"koth_team": -1, "koth_scoring": 0.0, "paused_ticks": 0, "game_start": 0.0}
        rules = [
            dict(base, tick=0, koth_start=0.0, koth_give_up=0.0),
            dict(base, tick=100, koth_start=900.0, koth_give_up=inf),
            dict(base, tick=110, koth_start=900.0, koth_give_up=960.0),
            dict(base, tick=6400, koth_start=0.0, koth_give_up=0.0),
        ]
        s = demo.summarize({"rejuv": [], "rules": rules, "midboss": []})
        self.assertEqual(s["koth"][0]["end_t"], 100)
        # Sin fila de cierre (koth_start no vuelve a 0) el fin no se puede determinar.
        s = demo.summarize({"rejuv": [], "rules": rules[:3], "midboss": []})
        self.assertIsNone(s["koth"][0]["end_t"])

    def test_summary_version_3(self):
        self.assertEqual(demo.SUMMARY_VERSION, 3)
        self.assertEqual(self.s["version"], 3)

    def test_midboss_no_damage(self):
        rejuv = [{"tick": 6400 + i * 6, "killing_team": 2, "user_team": 2} for i in range(3)]
        s = demo.summarize({"rejuv": rejuv, "rules": self.results["rules"], "midboss": []})
        self.assertEqual(len(s["midboss"]), 1)
        m = s["midboss"][0]
        self.assertIsNone(m["initiator"])
        self.assertIsNone(m["stolen"])
        self.assertEqual(m["rejuv"], {"0": 3, "1": 0})
        # Sin daño capturado: dato ausente, no ceros.
        self.assertIsNone(m["damage"])

    def test_rejuv_cluster_on_damage_entity_stolen(self):
        # El equipo 3 (API 1) hace el daño; el cúmulo de rejuvenators lo coge el 2 (API 0) -> robado.
        midboss = [{"victim": 7, "team": 3, "dmg": 12000, "t0": 3000, "t1": 6400}]
        rejuv = [{"tick": 6400 + 64 * 5 + i, "killing_team": 2, "user_team": 2} for i in range(3)]
        m = demo.summarize({"rejuv": rejuv, "rules": [], "midboss": midboss})["midboss"]
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["damage"], {"0": 0, "1": 12000})
        self.assertEqual((m[0]["initiator"], m[0]["killer"]), (1, 0))
        self.assertIs(m[0]["stolen"], True)

    def test_initiator_is_higher_damage_team(self):
        # El equipo 2 (API 0) golpea primero pero hace menos daño; el 3 (API 1) inicia y el 2 roba.
        midboss = [
            {"victim": 1, "team": 2, "dmg": 100, "t0": 1000, "t1": 6000},
            {"victim": 1, "team": 3, "dmg": 900, "t0": 2000, "t1": 6400},
        ]
        rejuv = [{"tick": 6500 + i, "killing_team": 2, "user_team": 2} for i in range(3)]
        rules = [{"tick": 0, "koth_team": 0, "koth_scoring": 0.0, "koth_start": 0.0,
                  "koth_give_up": 0.0, "paused_ticks": 0, "game_start": 0.0}]
        m = demo.summarize({"rejuv": rejuv, "rules": rules, "midboss": midboss})["midboss"][0]
        self.assertEqual(m["initiator"], 1)
        self.assertEqual(m["killer"], 0)
        self.assertIs(m["stolen"], True)

    def test_initiator_tie(self):
        midboss = [
            {"victim": 1, "team": 2, "dmg": 500, "t0": 1000, "t1": 6000},
            {"victim": 1, "team": 3, "dmg": 500, "t0": 2000, "t1": 6400},
        ]
        rejuv = [{"tick": 6500, "killing_team": 2, "user_team": 2}]
        m = demo.summarize({"rejuv": rejuv, "rules": [], "midboss": midboss})["midboss"][0]
        self.assertIsNone(m["initiator"])
        self.assertIsNone(m["stolen"])

    def test_summary_json_serializable(self):
        self.assertEqual(json.loads(json.dumps(self.s)), self.s)


# ---------------------------------------------------------------- cola y trabajador
import io
import tempfile
import urllib.error

from scouting import db, matches

if demo.AVAILABLE:
    from compression import zstd

RESULT_HOST = "https://demo-extracts.deadlock-api.com/"


class _Resp:
    def __init__(self, body):
        self._b = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self, n=-1):
        return self._b if n < 0 else self._b[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(url, code, body):
    return urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(body))


class FakeOpener:
    """Responde por URL; guarda cada petición (método, URL, cabeceras, cuerpo)."""

    def __init__(self, fixture, mode="ok", result_url=None):
        self.results = fixture["results"]
        self.mode = mode
        self.result_url = result_url
        self.calls = []
        self.jobs = {}

    def open(self, req, timeout=None):
        url = req.full_url
        self.calls.append({"method": req.get_method(), "url": url, "headers": dict(req.header_items()), "data": req.data})
        if req.get_method() == "POST":
            if self.mode == "404":
                raise _http_error(url, 404, b'{"error":"No demo available for match 1"}')
            if self.mode == "404salts":
                raise _http_error(url, 404, b'{"error":"Failed to fetch match salts for match 1"}')
            if self.mode == "404other":
                raise _http_error(url, 404, b'{"error":"otra cosa"}')
            if self.mode == "429":
                raise _http_error(url, 429, b"{}")
            body = json.loads(req.data)
            name = next(k for k, q in demo.QUERIES.items() if q == body["query"])
            self.jobs["j" + name] = name
            return _Resp({"job_id": "j" + name, "status": "queued"})
        if url.startswith("https://api.deadlock-api.com/v1/matches/demo/query/"):
            job = url.rsplit("/", 1)[1]
            if self.mode == "404poll":
                raise _http_error(url, 404, b'{"error":"No demo available for match 1"}')
            return _Resp({"status": "done", "result_url": self.result_url or f"{RESULT_HOST}{job}.ndjson.zst"})
        if url.startswith(RESULT_HOST):
            job = url.rsplit("/", 1)[1].split(".")[0]
            rows = self.results[self.jobs[job]]
            nd = "\n".join(json.dumps(r) for r in rows).encode()
            return _Resp(zstd.compress(nd))
        raise AssertionError("URL inesperada " + url)


@unittest.skipUnless(demo.AVAILABLE, "requiere compression.zstd (Python 3.14+)")
class Worker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = db.connect(os.path.join(self.tmp.name, "t.db"))
        self.addCleanup(self.con.close)
        old_dir = matches.MATCH_DIR
        matches.MATCH_DIR = os.path.join(self.tmp.name, "matches")
        self.addCleanup(setattr, matches, "MATCH_DIR", old_dir)
        old_hooks = list(matches.ON_STORE)
        self.addCleanup(lambda: matches.ON_STORE.__setitem__(slice(None), old_hooks))
        self.fixture = cargar()
        with open(LANE_FIXTURE, encoding="utf-8") as f:
            self.lane = json.load(f)["rows"]
        self.fixture["results"]["lane_damage"] = self.lane
        self.t = [1_000_000.0]

    def mk(self, mode="ok", result_url=None):
        self.op = FakeOpener(self.fixture, mode, result_url)
        self.client = demo.DemoClient(opener=self.op, now=lambda: self.t[0], sleep=lambda s: None)
        return demo.Worker(lambda: self.con, self.client)

    def test_enqueue_idempotent_and_keeps_done(self):
        demo.enqueue(self.con, 5)
        demo.enqueue(self.con, 5)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM demo_jobs").fetchone()[0], 1)
        self.con.execute("UPDATE demo_jobs SET state='done' WHERE match_id=5")
        demo.enqueue(self.con, 5)
        self.assertEqual(self.con.execute("SELECT state FROM demo_jobs").fetchone()[0], "done")

    def test_worker_success_stores_summary(self):
        w = self.mk()
        demo.enqueue(self.con, 135801973)
        self.assertTrue(w.step())
        s = demo.summary(self.con, 135801973)
        self.assertEqual(s["state"], "done")
        self.assertEqual(s["midboss"][0]["rejuv"], {"0": 0, "1": 3})
        self.assertEqual(len(self.op.calls), 12)
        for c in self.op.calls:
            h = {k.lower(): v for k, v in c["headers"].items()}
            self.assertEqual(h["user-agent"], "deadlock-scouting-local/1.0")

    def test_worker_stores_raw_results(self):
        w = self.mk()
        demo.enqueue(self.con, 135801973)
        w.step()
        raw = self.con.execute("SELECT raw FROM demo_jobs WHERE match_id=135801973").fetchone()[0]
        self.assertEqual(json.loads(raw)["rules"], self.fixture["results"]["rules"])

    def test_summary_resummarized_when_version_old(self):
        res = self.fixture["results"]
        viejo = {"version": demo.SUMMARY_VERSION - 1, "midboss": [], "koth": []}
        with self.con:
            self.con.execute("INSERT INTO demo_jobs(match_id, state, summary, raw, updated_at) VALUES(5, 'done', ?, ?, 0)",
                             (json.dumps(viejo), json.dumps(res)))
        s = demo.summary(self.con, 5)
        self.assertEqual(s["version"], demo.SUMMARY_VERSION)
        self.assertEqual(s["koth"], demo.summarize(res)["koth"])
        guardado = json.loads(self.con.execute("SELECT summary FROM demo_jobs WHERE match_id=5").fetchone()[0])
        self.assertEqual(guardado["version"], demo.SUMMARY_VERSION)

    def test_install_requeues_done_without_raw(self):
        with self.con:
            self.con.execute("INSERT INTO demo_jobs(match_id, state, summary, updated_at) VALUES(5, 'done', '{\"version\":1}', 0)")
            self.con.execute("INSERT INTO demo_jobs(match_id, state, summary, raw, updated_at) VALUES(6, 'done', '{}', '{}', 0)")
        demo.install(self.con, start_worker=False)
        estados = dict(self.con.execute("SELECT match_id, state FROM demo_jobs").fetchall())
        self.assertEqual(estados, {5: "pending", 6: "done"})

    def test_raw_column_migration_on_old_table(self):
        import sqlite3
        path = os.path.join(self.tmp.name, "viejo.db")
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE demo_jobs (match_id INTEGER PRIMARY KEY, state TEXT NOT NULL, summary TEXT, error TEXT, "
                  "attempts INTEGER NOT NULL DEFAULT 0, next_try INTEGER NOT NULL DEFAULT 0, updated_at INTEGER)")
        c.commit()
        c.close()
        con = db.connect(path)
        self.addCleanup(con.close)
        cols = [r[1] for r in con.execute("PRAGMA table_info(demo_jobs)")]
        self.assertIn("raw", cols)
        db.connect(path).close()  # idempotente

    def test_summarize_crash_is_fatal(self):
        w = self.mk()
        old = demo.summarize
        demo.summarize = lambda res: 1 / 0
        self.addCleanup(setattr, demo, "summarize", old)
        demo.enqueue(self.con, 7)
        w.step()
        r = self.con.execute("SELECT state, attempts FROM demo_jobs").fetchone()
        self.assertEqual(r["state"], "error")

    def test_truncated_result_rejected(self):
        # Un frame cortado descomprime sin error a b"" (0 filas): debe rechazarse, no tomarse por un resultado vacío.
        comp = zstd.compress(b"".join(json.dumps({"a": i}).encode() + b"\n" for i in range(3000)))
        self.assertEqual(len(demo.DemoClient._parse(comp)), 3000)
        with self.assertRaises(demo.DemoError):
            demo.DemoClient._parse(comp[:-1])

    def test_match_demo_endpoint(self):
        # GET /api/matches/{id}/demo: solo el estado del demo y las banderas de remontada (para el sondeo de la vista).
        from unittest import mock
        from scouting import server
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "match_109084310.json"), encoding="utf-8") as f:
            data = json.load(f)
        app = server.App(None, None, 0)
        app.con = lambda: self.con
        self.assertTrue(any(m == "GET" and p.match("/api/matches/109084310/demo") for m, p, _ in app.routes))
        with mock.patch.object(matches, "load", return_value=data):
            out = app.match_demo(None, "109084310")
            self.assertEqual(set(out), {"demo", "comeback", "lane_phase", "player_stats", "fights"})
            self.assertEqual(out["demo"]["state"], "pending")
            self.assertIsNone(out["comeback"])
            with self.con:
                self.con.execute("INSERT INTO demo_jobs(match_id, state, summary, raw, updated_at) VALUES(109084310, 'done', ?, '{}', 0)",
                                 (json.dumps({"version": demo.SUMMARY_VERSION, "midboss": [], "koth": [{"n": 1, "start_t": 600}]}),))
            out = app.match_demo(None, "109084310")
            self.assertEqual(out["demo"]["state"], "done")
            self.assertEqual(out["comeback"]["koth"], [matches.comeback_team_at(data["match_info"], 600)])

    def test_nodemo_404_not_retried(self):
        w = self.mk("404")
        demo.enqueue(self.con, 7)
        w.step()
        self.assertEqual(demo.summary(self.con, 7)["state"], "nodemo")
        n = len(self.op.calls)
        self.assertFalse(w.step())
        self.assertEqual(len(self.op.calls), n)

    def test_404_salts_is_nodemo(self):
        w = self.mk("404salts")
        demo.enqueue(self.con, 7)
        w.step()
        self.assertEqual(demo.summary(self.con, 7)["state"], "nodemo")

    def test_404_other_message_retries(self):
        w = self.mk("404other")
        demo.enqueue(self.con, 7)
        w.step()
        r = self.con.execute("SELECT state, attempts FROM demo_jobs").fetchone()
        self.assertEqual((r["state"], r["attempts"]), ("pending", 1))

    def test_404_on_poll_retries_not_nodemo(self):
        w = self.mk("404poll")
        demo.enqueue(self.con, 7)
        w.step()
        r = self.con.execute("SELECT state, attempts FROM demo_jobs").fetchone()
        self.assertEqual((r["state"], r["attempts"]), ("pending", 1))

    def test_error_sets_next_try_and_future_rows_skipped(self):
        w = self.mk("404other")
        demo.enqueue(self.con, 7)
        t = self.t[0]
        w.step()
        self.assertEqual(self.con.execute("SELECT next_try FROM demo_jobs").fetchone()[0], int(t + 600))
        n = len(self.op.calls)
        self.assertFalse(w.step())
        self.assertEqual(len(self.op.calls), n)
        self.t[0] += 601
        self.assertTrue(w.step())
        self.assertEqual(self.con.execute("SELECT next_try FROM demo_jobs").fetchone()[0], int(self.t[0] + 1200))

    def test_budget_and_pause_persist_across_restart(self):
        w = self.mk("429")
        demo.enqueue(self.con, 7)
        w.step()  # 1 POST + 429 -> pausa
        w2 = self.mk()
        self.assertEqual(w2.client.posts_last_hour(), 1)
        self.assertFalse(w2.step())  # sigue en pausa
        self.assertEqual(self.op.calls, [])

    def test_429_waits_and_keeps_pending(self):
        w = self.mk("429")
        demo.enqueue(self.con, 7)
        w.step()
        r = self.con.execute("SELECT state, next_try FROM demo_jobs").fetchone()
        self.assertEqual(r["state"], "pending")
        self.assertGreaterEqual(r["next_try"], self.t[0] + 61)

    def test_budget_150_per_hour(self):
        w = self.mk()
        self.client.post_times.extend([self.t[0] - 10] * 150)
        demo.enqueue(self.con, 7)
        self.assertFalse(w.step())
        self.assertEqual(self.op.calls, [])

    def test_result_url_other_host_rejected(self):
        w = self.mk(result_url="https://evil.example.com/x.ndjson.zst")
        demo.enqueue(self.con, 7)
        w.step()
        self.assertEqual(demo.summary(self.con, 7)["state"], "error")
        self.assertFalse(any("evil" in c["url"] for c in self.op.calls))

    def test_error_retries_then_gives_up(self):
        w = self.mk()
        w.client.run_queries = lambda mid: (_ for _ in ()).throw(OSError("caída"))
        demo.enqueue(self.con, 7)
        for i in range(5):
            self.t[0] += 10_000
            self.assertTrue(w.step())
        self.assertEqual(demo.summary(self.con, 7)["state"], "error")
        self.t[0] += 10_000_000
        self.assertFalse(w.step())

    def test_store_hook_enqueues(self):
        demo.install(self.con, start_worker=False)
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "match_109084310.json"), encoding="utf-8") as f:
            data = json.load(f)
        matches.store(self.con, data, "test")
        r = self.con.execute("SELECT state FROM demo_jobs WHERE match_id=109084310").fetchone()
        self.assertEqual(r["state"], "pending")

    def test_hook_failure_does_not_break_store(self):
        matches.ON_STORE.append(lambda con, mid: 1 / 0)
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "match_109084310.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(matches.store(self.con, data, "test"), 109084310)

    # ---- fase de líneas
    def _posts(self):
        return [json.loads(c["data"])["query"] for c in self.op.calls if c["method"] == "POST"]

    def _hecha_sin_lineas(self, mid=5):
        res = {k: v for k, v in self.fixture["results"].items() if k != "lane_damage"}
        with self.con:
            self.con.execute("INSERT INTO demo_jobs(match_id, state, summary, raw, updated_at) VALUES(?, 'done', ?, ?, 0)",
                             (mid, json.dumps(demo.summarize(res)), json.dumps(res)))
        return res

    def test_new_match_runs_four_queries(self):
        w = self.mk()
        demo.enqueue(self.con, 135801973)
        w.step()
        self.assertEqual(sorted(self._posts()), sorted(demo.QUERIES.values()))
        self.assertEqual(len(self._posts()), 4)
        self.assertEqual(demo.lane_rows(self.con, 135801973), self.lane)

    def test_done_row_backfills_only_lane_query(self):
        res = self._hecha_sin_lineas()
        antes = demo.summary(self.con, 5)
        w = self.mk()
        self.assertTrue(w.step())
        self.assertEqual(self._posts(), [demo.QUERIES["lane_damage"]])
        raw = json.loads(self.con.execute("SELECT raw FROM demo_jobs WHERE match_id=5").fetchone()[0])
        self.assertEqual(raw["lane_damage"], self.lane)
        self.assertEqual(raw["rules"], res["rules"])
        self.assertEqual(self.con.execute("SELECT state FROM demo_jobs").fetchone()[0], "done")
        self.assertEqual(demo.summary(self.con, 5), antes)
        n = len(self.op.calls)
        self.assertFalse(w.step())  # ya completa: nada más que hacer
        self.assertEqual(len(self.op.calls), n)

    def test_lane_rows_none_until_backfilled(self):
        self._hecha_sin_lineas()
        self.assertIsNone(demo.lane_rows(self.con, 5))
        self.assertIsNone(demo.lane_data(self.con, 5))
        self.assertIsNone(demo.lane_rows(self.con, 999))
        self.mk().step()
        self.assertEqual(demo.lane_rows(self.con, 5), self.lane)
        d = demo.lane_data(self.con, 5)
        self.assertEqual(d["rows"], self.lane)
        self.assertEqual(d["rules"], self.fixture["results"]["rules"])

    def test_backfill_error_keeps_done(self):
        self._hecha_sin_lineas()
        antes = demo.summary(self.con, 5)
        w = self.mk("404other")
        t = self.t[0]
        self.assertTrue(w.step())
        r = self.con.execute("SELECT state, attempts, lane_attempts, lane_next_try FROM demo_jobs").fetchone()
        self.assertEqual((r["state"], r["attempts"], r["lane_attempts"]), ("done", 0, 1))
        self.assertEqual(r["lane_next_try"], int(t + 600))
        self.assertEqual(demo.summary(self.con, 5), antes)
        self.assertFalse(w.step())  # en espera
        for _ in range(demo.MAX_ATTEMPTS - 1):
            self.t[0] += 100_000
            self.assertTrue(w.step())
        self.assertEqual(self.con.execute("SELECT state FROM demo_jobs").fetchone()[0], "done")
        self.t[0] += 100_000_000
        self.assertFalse(w.step())  # agotados los reintentos
        self.assertEqual(demo.summary(self.con, 5), antes)
        self.assertIsNone(demo.lane_rows(self.con, 5))

    def test_backfill_nodemo_marks_unavailable_once(self):
        self._hecha_sin_lineas()
        antes = demo.summary(self.con, 5)
        w = self.mk("404")
        self.assertTrue(w.step())
        self.assertEqual(self.con.execute("SELECT state FROM demo_jobs").fetchone()[0], "done")
        self.assertEqual(demo.summary(self.con, 5), antes)
        self.assertIsNone(demo.lane_data(self.con, 5))
        n = len(self.op.calls)
        self.t[0] += 100_000_000
        self.assertFalse(w.step())
        self.assertEqual(len(self.op.calls), n)

    def test_backfill_429_pauses_and_keeps_done(self):
        self._hecha_sin_lineas()
        w = self.mk("429")
        w.step()
        r = self.con.execute("SELECT state, lane_attempts, lane_next_try FROM demo_jobs").fetchone()
        self.assertEqual((r["state"], r["lane_attempts"]), ("done", 0))
        self.assertGreaterEqual(r["lane_next_try"], self.t[0] + 61)
        self.assertFalse(w.step())

    def test_pending_before_backfill_order(self):
        self._hecha_sin_lineas(900)  # id mayor que el pendiente, pero primero va lo pendiente
        demo.enqueue(self.con, 100)
        w = self.mk()
        w.step()
        self.assertEqual(len(self._posts()), 4)
        estados = dict(self.con.execute("SELECT match_id, state FROM demo_jobs").fetchall())
        self.assertEqual(estados, {100: "done", 900: "done"})
        self.assertIsNone(demo.lane_rows(self.con, 900))
        w.step()
        self.assertEqual(len(self._posts()), 5)
        self.assertEqual(demo.lane_rows(self.con, 900), self.lane)

    def test_backfill_order_match_id_desc(self):
        self._hecha_sin_lineas(5)
        self._hecha_sin_lineas(7)
        w = self.mk()
        w.step()
        self.assertIsNotNone(demo.lane_rows(self.con, 7))
        self.assertIsNone(demo.lane_rows(self.con, 5))

    def test_backfill_needs_one_post_of_budget(self):
        self._hecha_sin_lineas()
        w = self.mk()
        self.client.post_times.extend([self.t[0] - 10] * 149)
        self.assertTrue(w.step())
        self.assertEqual(len(self._posts()), 1)

    def test_saturated_budget_waits_for_pending_before_backfill(self):
        # Ventana llena: cada POST liberado no se gasta en relleno mientras haya una partida nueva esperando 4.
        self._hecha_sin_lineas(900)
        demo.enqueue(self.con, 100)
        t0 = self.t[0]
        w = self.mk()
        self.client.post_times[:] = [t0 - 3590, t0 - 3580, t0 - 3570, t0 - 3560] + [t0 - 10] * 146
        self.assertFalse(w.step())
        self.t[0] = t0 + 15  # 1 libre
        self.assertFalse(w.step())
        self.t[0] = t0 + 35  # 3 libres
        self.assertFalse(w.step())
        self.assertEqual(self._posts(), [])
        self.t[0] = t0 + 45  # 4 libres: va primero la pendiente
        self.assertTrue(w.step())
        self.assertEqual(len(self._posts()), 4)
        self.assertEqual(self.con.execute("SELECT state FROM demo_jobs WHERE match_id=100").fetchone()[0], "done")
        self.assertIsNone(demo.lane_rows(self.con, 900))

    def test_lane_limit_stored_with_rows(self):
        self._hecha_sin_lineas(5)
        demo.enqueue(self.con, 135801973)
        w = self.mk()
        w.step()
        w.step()
        for mid in (5, 135801973):
            raw = json.loads(self.con.execute("SELECT raw FROM demo_jobs WHERE match_id=?", (mid,)).fetchone()[0])
            self.assertEqual(raw["lane_damage_limit"], demo.LANE_TICK_LIMIT)
            self.assertEqual(demo.lane_data(self.con, mid)["limit"], demo.LANE_TICK_LIMIT)

    def test_lane_limit_defaults_to_legacy(self):
        res = dict(self.fixture["results"])
        with self.con:
            self.con.execute("INSERT INTO demo_jobs(match_id, state, raw, lane_state, updated_at) VALUES(5, 'done', ?, 'ok', 0)",
                             (json.dumps(res),))
        self.assertEqual(demo.lane_data(self.con, 5)["limit"], 48000)

    def test_backfill_empty_rows_not_stored(self):
        self._hecha_sin_lineas(5)
        self.fixture["results"]["lane_damage"] = []
        w = self.mk()
        self.assertTrue(w.step())
        self.assertEqual(tuple(self.con.execute("SELECT state, lane_state FROM demo_jobs").fetchone()), ("done", "vacio"))
        self.assertIsNone(demo.lane_data(self.con, 5))
        self.assertFalse(w.step())  # no se reintenta

    def test_new_match_empty_lane_rows_not_stored(self):
        self.fixture["results"]["lane_damage"] = []
        demo.enqueue(self.con, 135801973)
        self.mk().step()
        r = self.con.execute("SELECT state, lane_state FROM demo_jobs").fetchone()
        self.assertEqual((r["state"], r["lane_state"]), ("done", "vacio"))
        self.assertIsNone(demo.lane_data(self.con, 135801973))
        self.assertEqual(demo.summary(self.con, 135801973)["state"], "done")

    def test_lane_migration_on_old_table(self):
        import sqlite3
        path = os.path.join(self.tmp.name, "viejo2.db")
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE demo_jobs (match_id INTEGER PRIMARY KEY, state TEXT NOT NULL, summary TEXT, error TEXT, raw TEXT, "
                  "attempts INTEGER NOT NULL DEFAULT 0, next_try INTEGER NOT NULL DEFAULT 0, updated_at INTEGER)")
        c.execute("INSERT INTO demo_jobs(match_id, state, raw, updated_at) VALUES(1, 'done', '{}', 0)")
        c.commit()
        c.close()
        con = db.connect(path)
        self.addCleanup(con.close)
        cols = [r[1] for r in con.execute("PRAGMA table_info(demo_jobs)")]
        for col in ("lane_state", "lane_attempts", "lane_next_try"):
            self.assertIn(col, cols)
        self.assertEqual(tuple(con.execute("SELECT lane_attempts, lane_next_try FROM demo_jobs").fetchone()), (0, 0))
        db.connect(path).close()


class Unavailable(unittest.TestCase):
    def test_unavailable_without_zstd(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        con = db.connect(os.path.join(tmp.name, "u.db"))
        self.addCleanup(con.close)
        old = demo.AVAILABLE
        demo.AVAILABLE = False
        try:
            s = demo.summary(con, 1)
        finally:
            demo.AVAILABLE = old
        self.assertEqual(s["state"], "unavailable")
        self.assertIn("Python 3.14", s["reason"])

class ReportWithDemo(unittest.TestCase):
    OUR = 1

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "match_109084310.json"), encoding="utf-8") as f:
            cls.data = json.load(f)

    def summary(self, stolen=True):
        return {"state": "done", "version": 1,
                "midboss": [
                    {"n": 1, "t": 1237.0, "damage": {"0": 5000, "1": 9000}, "initiator": 1, "killer": 0, "stolen": stolen,
                     "rejuv": {"0": 1, "1": 2}},
                    {"n": 2, "t": 1751.0, "damage": {"0": 100, "1": 200}, "initiator": 1, "killer": 1, "stolen": False,
                     "rejuv": {"0": 0, "1": 3}},
                    {"n": 3, "t": 2236.0, "damage": {"0": 100, "1": 100}, "initiator": None, "killer": 0, "stolen": None,
                     "rejuv": {"0": 1, "1": 0}}],
                "koth": [{"n": 1, "start_t": 600.0, "completed_by": 1, "completed_t": 700.0},
                         {"n": 2, "start_t": 1500.0, "completed_by": 0, "completed_t": 1600.0},
                         {"n": 3, "start_t": 2000.0, "completed_by": None, "completed_t": None}]}

    def run_report(self, summaries):
        out = report.run("Prueba", [self.data], set(), side_overrides={109084310: self.OUR}, demo_summaries=summaries)
        return {s["id"]: s for s in out["sections"]}

    def test_comeback_rule(self):
        def mi(a, b):
            return {"players": [{"team": 0, "stats": [{"time_stamp_s": 60, "net_worth": a}]},
                                {"team": 1, "stats": [{"time_stamp_s": 60, "net_worth": b}]}]}
        self.assertEqual(matches.comeback_team_at(mi(9000, 10000), 100), matches.NO_COMEBACK)
        self.assertIsNone(matches.comeback_team_at({"players": [{"team": 0, "stats": []}, {"team": 1, "stats": []}]}, 100))
        self.assertIsNone(matches.comeback_team_at(mi(9000, 10000), None))
        self.assertEqual(matches.comeback_team_at(mi(8999, 10000), 100), 0)
        self.assertEqual(matches.comeback_team_at(mi(10000, 8999), 100), 1)

    def test_midboss_section_uses_demo(self):
        sec = self.run_report({109084310: self.summary(stolen=True)})["midboss"]
        tables = [b for b in sec["blocks"] if b["type"] == "table" and any(c["key"] == "rejuv_nuestros" for c in b["columns"])]
        self.assertEqual(len(tables), 1)
        keys = {c["key"] for c in tables[0]["columns"]}
        for k in ("rejuv_nuestros", "rejuv_rival", "dano_nuestro", "dano_rival", "iniciador", "robado", "remontada"):
            self.assertIn(k, keys)
        rows = tables[0]["rows"]
        self.assertEqual(rows[0]["robado"], "yes")
        self.assertEqual(rows[1]["robado"], "no")
        self.assertEqual(rows[2]["robado"], "—")
        self.assertEqual(rows[0]["rejuv_nuestros"], 2)
        self.assertEqual(rows[0]["dano_nuestro"], 9000)
        self.assertEqual(tables[0]["n"], 1)
        texts = " ".join(b.get("text", "") for b in sec["blocks"])
        self.assertIn("Demo data in 1 of 1 matches", texts)

    def test_midboss_section_without_demo(self):
        sec = self.run_report({})["midboss"]
        un = [b for b in sec["blocks"] if b["type"] == "unavailable" and "demo" in b["title"].lower()]
        self.assertTrue(un)
        self.assertTrue(any(b["type"] == "table" and b.get("title") == "Detail" for b in sec["blocks"]))

    def test_koth_section(self):
        sec = self.run_report({109084310: self.summary()})["koth"]
        tabs = [b for b in sec["blocks"] if b["type"] == "table"]
        self.assertTrue(tabs)
        detail = next(b for b in tabs if any(c["key"] == "remontada" for c in b["columns"]))
        self.assertEqual(detail["n"], 1)
        self.assertEqual([r["completa"] for r in detail["rows"]], ["This team", "Enemy", "Not completed"])
        self.assertTrue(all(r["remontada"] in ("yes", "no", "—") for r in detail["rows"]))

    def _remontadas(self, data, summ):
        out = report.run("Prueba", [data], set(), side_overrides={109084310: self.OUR}, demo_summaries={109084310: summ})
        secs = {s["id"]: s for s in out["sections"]}
        res = {}
        for sid in ("midboss", "koth"):
            tab = next(b for b in secs[sid]["blocks"] if b["type"] == "table" and any(c["key"] == "remontada" for c in b["columns"]))
            texts = " ".join(b.get("text", "") for b in secs[sid]["blocks"])
            res[sid] = ([r["remontada"] for r in tab["rows"]], tab["rows"], texts)
        return res

    def test_comeback_known_vs_unknown(self):
        import copy
        s = self.summary()
        known = self._remontadas(self.data, s)
        # Con muestras de net worth y equipo que lo mata/completa: «sí» o «no», nunca «—».
        self.assertTrue(all(v in ("yes", "no") for v in known["midboss"][0]))
        self.assertEqual([v in ("yes", "no") for v in known["koth"][0]], [True, True, False])
        sin = copy.deepcopy(self.data)
        for p in sin["match_info"]["players"]:
            p["stats"] = []
        unknown = self._remontadas(sin, s)
        self.assertEqual(unknown["midboss"][0], ["—"] * 3)
        self.assertEqual(unknown["koth"][0], ["—"] * 3)

    def test_comeback_text_says_net_worth(self):
        res = self._remontadas(self.data, self.summary())
        for sid in ("midboss", "koth"):
            self.assertIn("net worth (interpolated from the match samples) < 0.9 × the enemy's (10% rule)", res[sid][2])
            self.assertNotIn("almas del rival", res[sid][2])

    def test_midboss_without_damage_is_missing_not_zero(self):
        s = self.summary()
        s["midboss"][2]["damage"] = None
        rows = self._remontadas(self.data, s)["midboss"][1]
        self.assertIsNone(rows[2]["dano_nuestro"])
        self.assertIsNone(rows[2]["dano_rival"])

    def test_event_without_time_is_dash(self):
        s = self.summary()
        s["midboss"][0]["t"] = None
        s["koth"][0]["start_t"] = None
        res = self._remontadas(self.data, s)
        self.assertEqual(res["midboss"][0][0], "—")
        self.assertEqual(res["koth"][0][0], "—")

    def test_koth_without_demo(self):
        sec = self.run_report({})["koth"]
        self.assertTrue(any(b["type"] == "unavailable" for b in sec["blocks"]))


if __name__ == "__main__":
    unittest.main()
