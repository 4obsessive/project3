"""Tests de la estadística compartida, score v2, roles, climbers, actualizador e informe."""
import json
import os
import shutil
import tempfile
import time
import unittest

from scouting import analysis, db, images, players, roles, scoring, stats, summary, updater
from scouting.report import ReportCtx
from scouting.report.metricas import m99_conclusiones

try:
    from .test_scouting import FakeClient
except ImportError:  # discover -s tests
    from test_scouting import FakeClient


class Wilson(unittest.TestCase):
    def test_values(self):
        self.assertEqual(stats.wilson(0, 0), (0.0, 1.0))
        lo, hi = stats.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.237, places=3)
        self.assertAlmostEqual(hi, 0.763, places=3)

    def test_narrows_with_n(self):
        widths = [stats.wilson(n // 2, n)[1] - stats.wilson(n // 2, n)[0] for n in (10, 40, 160, 640)]
        self.assertEqual(widths, sorted(widths, reverse=True))


class Priors(unittest.TestCase):
    def test_beta_prior_fallback(self):
        self.assertEqual(stats.beta_prior([(10, 20)] * 7), (0.5, 30))
        # los pares con n < min_n no cuentan
        self.assertEqual(stats.beta_prior([(1, 2)] * 50), (0.5, 30))

    def test_beta_prior_clamp(self):
        # todos idénticos -> varianza real ~0 -> fuerza enorme, recortada a 200
        m, n = stats.beta_prior([(50, 100)] * 10)
        self.assertAlmostEqual(m, 0.5)
        self.assertEqual(n, 200)
        # muy dispersos -> fuerza mínima 15
        m, n = stats.beta_prior([(5, 100), (95, 100)] * 5)
        self.assertEqual(n, 15)

    def test_shrinkage_ordering(self):
        prior = (0.5, 30)
        small = stats.shrink_rate(3, 3, *prior)
        big = stats.shrink_rate(130, 200, *prior)
        self.assertLess(small, big)

    def test_reliability_boundaries(self):
        r = stats.reliability
        self.assertEqual([r(19), r(20), r(59), r(60), r(149), r(150)],
                         ["Insuficiente", "Baja", "Baja", "Media", "Media", "Alta"])

    def test_evidence(self):
        self.assertEqual(stats.evidence(2, 3)["evidence"], "indicio")
        self.assertEqual(stats.evidence(8, 9)["evidence"], "fuerte")


def _h(m, w=None, k=10, d=10, a=10, dmg=1000, t=1800, nwm=0.0, objm=0.0):
    return {"m": m, "w": m // 2 if w is None else w, "k": k, "d": d, "a": a, "dmg": dmg, "t": t, "nwm": nwm, "objm": objm}


class ScoreV2(unittest.TestCase):
    def test_support_at_baseline_is_one(self):
        base = scoring.baselines([{1: _h(10, k=10, d=10, a=40)}, {1: _h(10, k=10, d=10, a=40)}])
        idx = scoring.player_indices({1: _h(10, k=10, d=10, a=40)}, base)
        self.assertAlmostEqual(idx["kda"], 1.0)

    def test_provisional_and_zero_weights(self):
        rows = [{"n": n, "wr_adj": 0.5 + i / 100, "wr_lo": 0.4, "wr_hi": 0.6, "idx": {"kda": 1.0, "dmg": 1.0, "nw": 1.0, "obj": 1.0}, "pool": 2.0}
                for i, n in enumerate([1, 30, 40, 50])]
        scoring.score_all(rows)
        self.assertTrue(rows[0]["provisional"])
        self.assertFalse(rows[1]["provisional"])
        self.assertIsNone(scoring.score_from_parts(rows[1]["score_parts"], {k: 0 for k in scoring.DEFAULT_WEIGHTS}))
        self.assertLessEqual(rows[3]["score_lo"], rows[3]["score_default"])

    def test_effective_pool(self):
        self.assertAlmostEqual(scoring.effective_pool({1: _h(10), 2: _h(10), 3: _h(2)}), 2.0)


class Roles(unittest.TestCase):
    def test_time_weighted(self):
        table, thr = roles.load_table()
        rbh = roles.hero_roles(table, {2: "Bebop", 3: "Wraith"})
        # mismas partidas, pero Wraith con el triple de tiempo
        main, br = roles.player_roles({2: 1000, 3: 3000}, rbh, thr)
        self.assertEqual(main[0], "Carry")


class Climbers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = db.connect(os.path.join(self.tmp, "t.db"))

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_relative_fallers_dropped_size(self):
        con = self.con
        db.kv_set(con, "current_leaderboard_id", 1002)
        now = int(time.time())
        p = {k: players.create_player(con, 20000 + i, k, "leaderboard") for i, k in enumerate(["top", "mid", "fall", "gone"])}
        old = {"top": 12, "mid": 900, "fall": 5, "gone": 50}
        new = {"top": 4, "mid": 700, "fall": 40}
        for t, ranks, size in ((now - 8 * 86400, old, 1000), (now, new, 600)):
            sid = con.execute("INSERT INTO lb_snapshots(leaderboard_id, region, taken_at, n_entries) VALUES(1002,'Europe',?,?)", (t, size)).lastrowid
            for k, r in ranks.items():
                con.execute("INSERT INTO lb_entries(snapshot_id, rank, player_id) VALUES(?,?,?)", (sid, r, p[k]))
        out = analysis.climbers(con, 7)
        self.assertEqual([c["player_id"] for c in out["climbers"]], [p["top"], p["mid"]])
        self.assertEqual([c["player_id"] for c in analysis.climbers(con, 7, "pos")["climbers"]], [p["mid"], p["top"]])
        self.assertEqual([c["player_id"] for c in out["fallers"]], [p["fall"]])
        self.assertEqual([c["player_id"] for c in out["dropped"]], [p["gone"]])
        self.assertIsNotNone(out["size_warning"])


class UpdaterWindow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "t.db")
        self.con = db.connect(self.path)
        teams = os.path.join(self.tmp, "equipos.txt")
        with open(teams, "w", encoding="utf-8") as f:
            f.write("222222 Buff Enjoyers\n")
        self._orig = updater.config.TEAMS_PATH, updater.config.load
        updater.config.TEAMS_PATH = teams
        updater.config.load = lambda: dict(updater.config.DEFAULTS, extra_leaderboard_ids=[1001], batch_size=2)

    def tearDown(self):
        updater.config.TEAMS_PATH, updater.config.load = self._orig
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resumed_window_ends_now(self):
        u0 = updater.Updater(FakeClient(), db_path=self.path)
        u0.con = lambda: self.con
        u0._run_safe("test")
        old_start = int(time.time()) - 5 * 3600
        with self.con:
            self.con.execute("DELETE FROM stats_fetched")
            self.con.execute("INSERT INTO jobs(kind,state,step,started_at) VALUES('update','interrupted','stats',?)", (old_start,))
        c = FakeClient()
        u = updater.Updater(c, db_path=self.path)
        u.con = lambda: self.con
        u._run_safe("test")
        self.assertIsNone(u.status["error"])
        # ventana anclada a "ahora", no al inicio del trabajo reanudado
        self.assertGreater(min(c.windows), int(time.time()) - 30 * 86400 - 60)
        self.assertTrue(all(m == "ranked" for m in c.modes))
        end = int(db.kv_get(self.con, "stats_window_end"))
        self.assertGreater(end, old_start + 3600)

    def test_badges_and_steam(self):
        u = updater.Updater(FakeClient(), db_path=self.path)
        u.con = lambda: self.con
        u._run_safe("test")
        self.assertGreater(self.con.execute("SELECT COUNT(*) FROM badge_history").fetchone()[0], 0)
        # perfiles de Steam también para cuentas de la leaderboard
        r = self.con.execute("SELECT personaname FROM steam_profiles WHERE account_id=333333").fetchone()
        self.assertIsNotNone(r)
        data = {p["name"]: p for p in json.loads(summary.all_json(self.con))}
        self.assertEqual(data["Alfa"]["badge"], 105)
        self.assertIsNotNone(data["Alfa"]["score_parts"])
        self.assertIsNotNone(data["Alfa"]["stats"]["wr_adj"])

    def test_small_sample_roles(self):
        # 32 partidas: hay roles; un jugador sin partidas no
        u = updater.Updater(FakeClient(), db_path=self.path)
        u.con = lambda: self.con
        u._run_safe("test")
        pid = players.create_player(self.con, 999991, "Vacío", "manual")
        summary.materialize(self.con)
        s = summary.get_one(self.con, pid)
        self.assertEqual(s["roles"], [])
        self.assertEqual(s["role_text"], "muestra insuficiente")

    def test_migration_adds_columns(self):
        path = os.path.join(self.tmp, "old.db")
        import sqlite3
        raw = sqlite3.connect(path)
        raw.execute("CREATE TABLE hero_stats (account_id INTEGER NOT NULL, hero_id INTEGER NOT NULL, matches INTEGER, wins INTEGER, "
                    "kills INTEGER, deaths INTEGER, assists INTEGER, player_damage INTEGER, damage_taken INTEGER, boss_damage INTEGER, "
                    "creep_damage INTEGER, obj_damage_per_min REAL, damage_per_min REAL, networth_per_min REAL, accuracy REAL, "
                    "time_played INTEGER, last_played INTEGER, PRIMARY KEY (account_id, hero_id))")
        raw.execute("INSERT INTO hero_stats(account_id, hero_id, matches) VALUES(1, 2, 3)")
        raw.commit()
        raw.close()
        con = db.connect(path)
        cols = {r[1] for r in con.execute("PRAGMA table_info(hero_stats)")}
        self.assertIn("last_hits_per_min", cols)
        self.assertEqual(con.execute("SELECT matches FROM hero_stats").fetchone()[0], 3)
        con.close()


class ReportEvidence(unittest.TestCase):
    def test_levels_and_baseline(self):
        ctx = ReportCtx("x", [], {}, [])
        self.assertEqual(ctx.finding("pattern", "a", 2, 3)["evidence"], "indicio")
        self.assertEqual(ctx.finding("pattern", "b", 8, 9)["evidence"], "fuerte")
        # 4/6 con base 1/3 (tres carriles) es moderada; con base 1/2 es solo indicio
        self.assertEqual(ctx.finding("weakness", "c", 4, 6, baseline=1 / 3)["evidence"], "moderada")
        self.assertEqual(ctx.finding("weakness", "d", 4, 6)["evidence"], "indicio")
        order = sorted(ctx.findings, key=m99_conclusiones.sort_key)
        self.assertEqual(order[0]["text"], "b")
        self.assertIn("IC90", m99_conclusiones.evidence_text(order[0]))

    def test_side_comparison_needs_five(self):
        from scouting.report.metricas import m01_resumen
        src = open(m01_resumen.__file__, encoding="utf-8").read()
        self.assertIn("n >= 5 and on >= 5", src)


class SteamImages(unittest.TestCase):
    def test_steam_names(self):
        h = "58de1e6c00774674ef9cd02d9a9c0ee91bdd8bcf"
        for ok in (h + ".jpg", h + "_medium.jpg", h + "_full.jpg"):
            self.assertEqual(images.safe_name("steam", ok), ok)
        for bad in ("../" + h + ".jpg", h + ".png", h[:-1] + ".jpg", h.upper() + ".jpg", h + "_full.jpg/x", "a/" + h + ".jpg", h + ".jpeg"):
            self.assertIsNone(images.safe_name("steam", bad), bad)
        self.assertEqual(images.steam_avatar_path(f"https://avatars.steamstatic.com/{h}_full.jpg"), f"/img/steam/{h}_medium.jpg")
        self.assertIsNone(images.steam_avatar_path(f"https://evil.example/{h}.jpg"))


if __name__ == "__main__":
    unittest.main()
