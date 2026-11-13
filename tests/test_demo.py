import json
import os
import unittest

from scouting import demo, report

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "demo_135801973.json")


def cargar():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class Summarize(unittest.TestCase):
    def setUp(self):
        self.data = cargar()
        self.results = self.data["results"]
        self.s = demo.summarize(self.results)

    def test_queries_match_fixture(self):
        self.assertEqual(demo.QUERIES, self.data["queries"])

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

    def test_midboss_no_damage(self):
        rejuv = [{"tick": 6400 + i * 6, "killing_team": 2, "user_team": 2} for i in range(3)]
        s = demo.summarize({"rejuv": rejuv, "rules": self.results["rules"], "midboss": []})
        self.assertEqual(len(s["midboss"]), 1)
        m = s["midboss"][0]
        self.assertIsNone(m["initiator"])
        self.assertIsNone(m["stolen"])
        self.assertEqual(m["rejuv"], {"0": 3, "1": 0})

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
        self.assertEqual(len(self.op.calls), 9)
        for c in self.op.calls:
            h = {k.lower(): v for k, v in c["headers"].items()}
            self.assertEqual(h["user-agent"], "deadlock-scouting-local/1.0")

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
        self.assertIsNone(matches.comeback_team_at(mi(9000, 10000), 100))
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
        self.assertEqual(rows[0]["robado"], "sí")
        self.assertEqual(rows[1]["robado"], "no")
        self.assertEqual(rows[2]["robado"], "—")
        self.assertEqual(rows[0]["rejuv_nuestros"], 2)
        self.assertEqual(rows[0]["dano_nuestro"], 9000)
        self.assertEqual(tables[0]["n"], 1)
        texts = " ".join(b.get("text", "") for b in sec["blocks"])
        self.assertIn("Datos del demo en 1 de 1 partidas", texts)

    def test_midboss_section_without_demo(self):
        sec = self.run_report({})["midboss"]
        un = [b for b in sec["blocks"] if b["type"] == "unavailable" and "demo" in b["title"].lower()]
        self.assertTrue(un)
        self.assertTrue(any(b["type"] == "table" and b.get("title") == "Detalle" for b in sec["blocks"]))

    def test_koth_section(self):
        sec = self.run_report({109084310: self.summary()})["koth"]
        tabs = [b for b in sec["blocks"] if b["type"] == "table"]
        self.assertTrue(tabs)
        detail = next(b for b in tabs if any(c["key"] == "remontada" for c in b["columns"]))
        self.assertEqual(detail["n"], 1)
        self.assertEqual([r["completa"] for r in detail["rows"]], ["Este equipo", "Rival", "No completado"])
        self.assertTrue(all(r["remontada"] in ("sí", "no", "—") for r in detail["rows"]))

    def test_koth_without_demo(self):
        sec = self.run_report({})["koth"]
        self.assertTrue(any(b["type"] == "unavailable" for b in sec["blocks"]))


if __name__ == "__main__":
    unittest.main()
