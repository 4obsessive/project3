import json
import os
import unittest

from scouting import demo

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


if __name__ == "__main__":
    unittest.main()


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
                raise urllib.error.HTTPError(url, 404, "nf", {}, io.BytesIO(b'{"error":"No demo available for match 1"}'))
            if self.mode == "429":
                raise urllib.error.HTTPError(url, 429, "slow", {}, io.BytesIO(b"{}"))
            body = json.loads(req.data)
            name = next(k for k, q in demo.QUERIES.items() if q == body["query"])
            self.jobs["j" + name] = name
            return _Resp({"job_id": "j" + name, "status": "queued"})
        if url.startswith("https://api.deadlock-api.com/v1/matches/demo/query/"):
            job = url.rsplit("/", 1)[1]
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
