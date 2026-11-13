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


if __name__ == "__main__":
    unittest.main()
