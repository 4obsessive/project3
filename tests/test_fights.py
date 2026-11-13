import gzip
import json
import math
import os
import unittest

from scouting import demo, fights, matches

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "tests", "fixtures")


def mi_con(destroyed=(), deaths=()):
    """Metadata mínima: un jugador (slot 0) con las muertes dadas como (t, x, y)."""
    dd = [{"game_time_s": t, "death_pos": ({"x": x, "y": y} if x is not None else None), "killer_player_slot": 1}
          for t, x, y in deaths]
    return {"mid_boss": [{"destroyed_time_s": d} for d in destroyed],
            "players": [{"player_slot": 0, "team": 0, "hero_id": 1, "account_id": 1, "death_details": dd},
                        {"player_slot": 1, "team": 1, "hero_id": 2, "account_id": 2, "death_details": []}]}


def clases(mi, summ=None):
    r = fights.classify(mi, summ)
    return r["koth_known"], [e["fight"] for e in r["events"]]


def summ(midboss=(), koth=()):
    return {"state": "done", "midboss": list(midboss), "koth": list(koth)}


class Classify(unittest.TestCase):
    def test_constants(self):
        self.assertEqual((fights.MIDBOSS_RADIUS, fights.RIFT_RADIUS, fights.AFTER_S), (2500, 2000, 60))
        self.assertEqual(fights.RIFTS, [(-7648, 0), (7648, 0)])
        self.assertEqual(fights.PIT, (0, 0))

    def test_midboss_demo_window(self):
        s = summ(midboss=[{"n": 1, "t": 1200, "t_first": 1185}])
        for t, esp in [(1184, "rest"), (1185, "midboss"), (1260, "midboss"), (1261, "rest")]:
            self.assertEqual(clases(mi_con(deaths=[(t, 100, 100)]), s)[1], [esp], t)

    def test_midboss_radius(self):
        s = summ(midboss=[{"n": 1, "t": 1200, "t_first": 1185}])
        self.assertEqual(clases(mi_con(deaths=[(1200, 2400, 0)]), s)[1], ["midboss"])
        self.assertEqual(clases(mi_con(deaths=[(1200, 2600, 0)]), s)[1], ["rest"])

    def test_midboss_without_demo(self):
        mi = mi_con(destroyed=[1000], deaths=[(939, 0, 0), (940, 0, 0), (1060, 0, 0), (1061, 0, 0)])
        self.assertEqual(clases(mi)[1], ["rest", "midboss", "midboss", "rest"])
        self.assertEqual(clases(mi, {"state": "pending"})[1], ["rest", "midboss", "midboss", "rest"])

    def test_midboss_rejuv_only_uses_destroyed_window(self):
        s = summ(midboss=[{"n": 1, "t": 1000, "t_first": None}])
        mi = mi_con(deaths=[(940, 0, 0), (939, 0, 0)])
        self.assertEqual(clases(mi, s)[1], ["rest", "midboss"])

    def test_koth_window(self):
        s = summ(koth=[{"n": 1, "start_t": 740, "completed_t": 758, "end_t": 758}])
        for t, esp in [(739, "rest"), (740, "koth"), (758 + 59, "koth"), (758 + 60, "koth"), (758 + 61, "rest")]:
            self.assertEqual(clases(mi_con(deaths=[(t, -7500, 100)]), s)[1], [esp], t)
        self.assertEqual(clases(mi_con(deaths=[(750, 7000, 0)]), s)[1], ["koth"])

    def test_koth_radius_and_far(self):
        s = summ(koth=[{"n": 1, "start_t": 740, "end_t": 758}])
        self.assertEqual(clases(mi_con(deaths=[(750, -7648 + 1900, 0)]), s)[1], ["koth"])
        self.assertEqual(clases(mi_con(deaths=[(750, -7648 + 2100, 0)]), s)[1], ["rest"])
        self.assertEqual(clases(mi_con(deaths=[(750, 0, 5000)]), s)[1], ["rest"])

    def test_koth_end_none_fixed_window(self):
        s = summ(koth=[{"n": 1, "start_t": 1000, "completed_t": None, "end_t": None}])
        mi = mi_con(deaths=[(1120, 7648, 0), (1121, 7648, 0)])
        self.assertEqual(clases(mi, s)[1], ["koth", "rest"])

    def test_koth_unknown_without_demo(self):
        known, cl = clases(mi_con(deaths=[(750, -7648, 0)]))
        self.assertFalse(known)
        self.assertEqual(cl, ["rest"])
        self.assertTrue(clases(mi_con(), summ())[0])

    def test_both_windows_nearest(self):
        # (-1000,0) y (-1700,0) caben en el radio del pit; el rift queda a >2000 -> midboss. Para solapar
        # se usa un radio-borde: nada solapa de verdad, así que se comprueba el desempate con funciones.
        self.assertEqual(fights._nearest_objective(100, 0), "midboss")
        self.assertEqual(fights._nearest_objective(-6000, 0), "koth")

    def test_both_windows_same_time(self):
        s = summ(midboss=[{"n": 1, "t": 1000, "t_first": 990}], koth=[{"n": 1, "start_t": 990, "end_t": 1000}])
        self.assertEqual(clases(mi_con(deaths=[(1000, -2400, 0)]), s)[1], ["midboss"])
        self.assertEqual(clases(mi_con(deaths=[(1000, -5700, 0)]), s)[1], ["koth"])

    def test_unknown_without_position(self):
        s = summ(midboss=[{"n": 1, "t": 1000, "t_first": 990}])
        self.assertEqual(clases(mi_con(deaths=[(1000, None, None)]), s)[1], ["unknown"])
        mi = mi_con(deaths=[(1000, 0, 0)])
        mi["players"][0]["death_details"][0]["death_pos"] = {"x": 5}
        self.assertEqual(clases(mi, s)[1], ["unknown"])

    def test_event_fields_kept(self):
        r = fights.classify(mi_con(deaths=[(10, 1, 2)]))["events"][0]
        self.assertEqual((r["t"], r["x"], r["y"], r["victim_slot"], r["fight"]), (10, 1, 2, 0, "rest"))


class RealMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(os.path.join(FX, "match_135801973.json.gz"), "rt", encoding="utf-8") as f:
            cls.mi = json.load(f)["match_info"]
        with open(os.path.join(FX, "demo_135801973.json"), encoding="utf-8") as f:
            res = json.load(f)["results"]
        cls.summ = dict(demo.summarize(res), state="done")

    def test_counts_consistent(self):
        r = fights.classify(self.mi, self.summ)
        total = len(matches.deaths(self.mi))
        self.assertEqual(len(r["events"]), total)
        self.assertTrue(r["koth_known"])
        cnt = {}
        for e in r["events"]:
            cnt[e["fight"]] = cnt.get(e["fight"], 0) + 1
        self.assertEqual(sum(cnt.values()), total)
        self.assertTrue(set(cnt) <= {"midboss", "koth", "rest", "unknown"})
        for e in r["events"]:
            if e["fight"] == "midboss":
                self.assertLessEqual(math.hypot(e["x"], e["y"]), 2500)
            if e["fight"] == "koth":
                self.assertLessEqual(min(math.hypot(e["x"] - rx, e["y"]) for rx, _ in fights.RIFTS), 2000)

    def test_without_demo(self):
        r = fights.classify(self.mi)
        self.assertFalse(r["koth_known"])
        self.assertFalse(any(e["fight"] == "koth" for e in r["events"]))
        self.assertEqual(len(r["events"]), len(matches.deaths(self.mi)))


class Split(unittest.TestCase):
    """Reparto en player_stats, informe y payload: mismos números que classify."""
    MID = 135801973

    @classmethod
    def setUpClass(cls):
        with gzip.open(os.path.join(FX, "match_135801973.json.gz"), "rt", encoding="utf-8") as f:
            cls.mi = json.load(f)["match_info"]
        with open(os.path.join(FX, "demo_135801973.json"), encoding="utf-8") as f:
            res = json.load(f)["results"]
        cls.summ = dict(demo.summarize(res), state="done")

    def test_counts_helper(self):
        r = fights.classify(self.mi, self.summ)
        c = fights.counts(r)
        self.assertEqual(set(c), {"midboss", "koth", "rest", "unknown"})
        self.assertEqual(sum(c.values()), len(r["events"]))

    def test_player_stats_rest(self):
        from scouting import playerstats
        r = fights.classify(self.mi, self.summ)
        ps = playerstats.player_stats(self.mi, None, fights=r)
        ev = r["events"]
        for p in ps:
            k = [e for e in ev if e["killer_slot"] == p["slot"] and e["killer_team"] != e["victim_team"]]
            d = [e for e in ev if e["victim_slot"] == p["slot"]]
            self.assertEqual(p["kills_rest"], sum(1 for e in k if e["fight"] == "rest"))
            self.assertEqual(p["deaths_rest"], sum(1 for e in d if e["fight"] == "rest"))
            self.assertLessEqual(sum(n for _, _, n in p["kill_cells_rest"]), p["kills_rest"])
            self.assertEqual(p["fights"]["deaths"]["rest"], p["deaths_rest"])
            self.assertEqual(sum(p["fights"]["deaths"].values()), len(d))
            self.assertEqual(sum(p["fights"]["kills"].values()), len(k))

    def test_player_stats_without_koth(self):
        from scouting import playerstats
        for fx in (None, fights.classify(self.mi)):
            for p in playerstats.player_stats(self.mi, None, fights=fx):
                for k in ("kills_rest", "deaths_rest", "kill_cells_rest", "death_cells_rest"):
                    self.assertIsNone(p[k])

    def test_payload_has_fights(self):
        import tempfile
        from scouting import db, server
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(os.path.join(tmp, "t.db"))
            out = server.match_payload_extras(con, self.MID, self.mi)
            con.close()
        self.assertEqual(out["fights"]["koth_known"], False)
        self.assertEqual(out["fights"]["counts"], fights.counts(fights.classify(self.mi)))
        self.assertEqual(len(out["fights"]["labels"]), len(matches.deaths(self.mi)))


class ReportSplit(unittest.TestCase):
    MID = 135801973

    @classmethod
    def setUpClass(cls):
        Split.setUpClass.__func__(cls)
        cls.roster = {p["account_id"] for p in cls.mi["players"] if p["team"] == 1}

    def run_report(self, with_demo=True, mis=None):
        from scouting import report
        datas = [{"match_info": cls_mi} for cls_mi in (mis or [self.mi])]
        sm = {self.MID: self.summ} if with_demo else {}
        out = report.run("T", datas, self.roster, side_overrides={self.MID: 1}, demo_summaries=sm)
        return {s["id"]: s for s in out["sections"]}

    def test_m02_totals_match_classify(self):
        sec = self.run_report()["mapa"]
        self.assertNotIn("error", sec)
        c = fights.counts(fights.classify(self.mi, self.summ))
        tb = next(b for b in sec["blocks"] if b.get("kind") == "fight_split")
        rows = {r["tipo"]: r for r in tb["rows"]}
        for k in ("midboss", "koth", "rest", "unknown"):
            self.assertEqual(rows[k]["kills"] + rows[k]["deaths"], c[k], k)
        mp = next(b for b in sec["blocks"] if b.get("kind") == "rest_map")
        pts = sum(len(l["points"]) for l in mp["layers"])
        self.assertEqual(pts, c["rest"])

    def test_m02_excludes_match_without_demo(self):
        sec = self.run_report(with_demo=False)["mapa"]
        txt = [b["text"] for b in sec["blocks"] if b.get("kind") == "fight_excluded"]
        self.assertEqual(len(txt), 1)
        self.assertIn("1 of 1 matches excluded", txt[0])
        self.assertFalse(any(b.get("kind") in ("fight_split", "rest_map") for b in sec["blocks"]))

    def test_m08_rest_per_player(self):
        from scouting import playerstats
        sec = self.run_report()["jugadores"]
        tb = next(b for b in sec["blocks"] if b.get("kind") == "jugadores")
        ps = {p["account_id"]: p for p in playerstats.player_stats(self.mi, None, fights=fights.classify(self.mi, self.summ))}
        for r in tb["rows"]:
            p = ps[r["account_id"]]
            self.assertEqual(r["kills_rest"], round(p["kills_rest"], 1))
            self.assertEqual(r["deaths_rest"], round(p["deaths_rest"], 1))
            self.assertEqual(r["n_rest"], 1)

    def test_m08_mixed_demo_and_no_demo(self):
        import copy
        from scouting import playerstats
        mi2 = copy.deepcopy(self.mi)
        mi2["match_id"] = self.MID + 1
        sec = self.run_report(mis=[self.mi, mi2])["jugadores"]
        tb = next(b for b in sec["blocks"] if b.get("kind") == "jugadores")
        ps = {p["account_id"]: p for p in playerstats.player_stats(self.mi, None, fights=fights.classify(self.mi, self.summ))}
        for r in tb["rows"]:
            self.assertEqual(r["n"], 2)
            self.assertEqual(r["n_rest"], 1)
            self.assertEqual(r["kills_rest"], round(ps[r["account_id"]]["kills_rest"], 1))


if __name__ == "__main__":
    unittest.main()
