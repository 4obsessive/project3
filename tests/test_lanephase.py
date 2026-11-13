"""Fase de líneas: línea de cada jugador por posiciones y duos."""
import copy
import gzip
import json
import os
import unittest

from scouting import demo, lanes, lanephase, matches

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "match_135801973.json.gz")

ESPERADO = {298155885: 3, 888853854: 3, 298305257: 4, 984254212: 4, 906011648: 1, 5278896: 1,
            483770846: 1, 35187362: 1, 911856667: 4, 97533101: 4, 87241154: 3, 344946432: 3}


def _mi():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as f:
        return json.load(f)["match_info"]


class Lanes(unittest.TestCase):
    def setUp(self):
        self.mi = _mi()
        self.paths = lanes.load_paths()
        self.slot = {p["account_id"]: p["player_slot"] for p in self.mi["players"]}

    def test_assign_lanes_real_match(self):
        res = lanes.assign_lanes(self.mi, self.paths)
        for acc, lane in ESPERADO.items():
            self.assertEqual(res[self.slot[acc]], lane, acc)

    def test_duos_two_per_lane(self):
        res = lanes.assign_lanes(self.mi, self.paths)
        d = lanes.duos(self.mi, res)
        self.assertEqual(sorted(d), [0, 1])
        for team in (0, 1):
            self.assertEqual(sorted(d[team]), [1, 3, 4])
            for lane in (1, 3, 4):
                self.assertEqual(len(d[team][lane]), 2)

    def test_invalid_when_not_two_and_two(self):
        mi = copy.deepcopy(self.mi)
        paths = mi["match_paths"]["paths"]
        # Copia las posiciones de un jugador de la línea 3 al de otro de la línea 1 del mismo equipo.
        slot_a = self.slot[298155885]
        slot_b = next(p["player_slot"] for p in mi["players"]
                      if p["team"] == next(q["team"] for q in mi["players"] if q["account_id"] == 298155885)
                      and ESPERADO[p["account_id"]] == 1)
        src = next(q for q in paths if q["player_slot"] == slot_a)
        dst = next(q for q in paths if q["player_slot"] == slot_b)
        for k in ("x_pos", "y_pos", "health", "x_min", "x_max", "y_min", "y_max"):
            dst[k] = copy.deepcopy(src[k])
        res = lanes.assign_lanes(mi, self.paths)
        self.assertTrue(all(v is None for v in res.values()))
        self.assertEqual(lanes.duos(mi, res), {})

    def test_player_without_positions(self):
        mi = copy.deepcopy(self.mi)
        q = mi["match_paths"]["paths"][0]
        q["health"] = [0] * len(q["x_pos"])
        res = lanes.assign_lanes(mi, self.paths)
        self.assertTrue(all(v is None for v in res.values()))
        self.assertEqual(lanes.duos(mi, res), {})

FX = os.path.join(ROOT, "tests", "fixtures")


def _load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


class LanePhase(unittest.TestCase):
    def setUp(self):
        self.mi = _mi()
        self.rows = _load("demo_lane_135801973.json")["rows"]
        self.rules = _load("demo_135801973.json")["results"]["rules"]
        self.slot = {p["account_id"]: p["player_slot"] for p in self.mi["players"]}
        self.team = {p["player_slot"]: p["team"] for p in self.mi["players"]}
        self.lane = {self.slot[a]: l for a, l in ESPERADO.items()}
        self.res = lanephase.lane_phase(self.mi, self.rows, self.rules)

    def _timed(self):
        for r in self.rows:
            a, v = self.slot[r["att"]], self.slot[r["vic"]]
            t = demo.game_seconds_from_tick(r["b"] * 320, self.rules)
            if self.team[a] != self.team[v] and 0 <= t <= 600:
                yield t, a, v, r["dmg"]

    def test_valid_and_source_demo(self):
        self.assertTrue(self.res["valid"])
        self.assertEqual(self.res["source"], "demo")
        self.assertEqual(set(self.res["lanes"]), {"1", "3", "4"})
        for ln in self.res["lanes"].values():
            self.assertEqual(set(ln), {"0", "1"})
            for d in ln.values():
                self.assertEqual(len(d["slots"]), 2)

    def test_dmg_sums_match_rows(self):
        for slot in self.team:
            done = sum(d for t, a, v, d in self._timed() if a == slot)
            taken = sum(d for t, a, v, d in self._timed() if v == slot)
            self.assertEqual(self.res["players"][str(slot)]["dmg_done"], done)
            self.assertEqual(self.res["players"][str(slot)]["dmg_taken"], taken)
        self.assertGreater(sum(p["dmg_done"] for p in self.res["players"].values()), 0)

    def test_lane_split_adds_up(self):
        for ln, teams in self.res["lanes"].items():
            for tm, d in teams.items():
                self.assertEqual(d["dmg_taken"], d["dmg_taken_lane"] + d["dmg_taken_gank"])
                exp_lane = sum(x for t, a, v, x in self._timed()
                               if v in d["slots"] and self.lane[a] == self.lane[v])
                self.assertEqual(d["dmg_taken_lane"], exp_lane)

    def test_first_gank_is_cross_lane_and_after_60(self):
        kills = {(k["t"], k["killer_slot"], k["victim_slot"]) for k in matches.deaths(self.mi)}
        seen = 0
        for ln, teams in self.res["lanes"].items():
            for tm, d in teams.items():
                g = d["first_gank_suffered"]
                if g is None:
                    continue
                seen += 1
                self.assertNotEqual(self.lane[g["attacker_slot"]], self.lane[g["victim_slot"]])
                self.assertEqual(self.lane[g["victim_slot"]], int(ln))
                self.assertIn(g["victim_slot"], d["slots"])
                self.assertTrue(60 <= g["t"] <= 600)
                earlier = [t for t, a, v, x in self._timed()
                           if x > 0 and t >= 60 and v in d["slots"] and self.lane[a] != int(ln)]
                earlier += [k[0] for k in kills if k[2] in d["slots"] and k[1] is not None
                            and self.team[k[1]] != int(tm) and self.lane[k[1]] != int(ln) and 60 <= k[0] <= 600]
                self.assertEqual(g["t"], round(min(earlier)))
                # el gankeo hecho del rival en esa línea es el mismo evento
                self.assertEqual(self.res["lanes"][ln][str(1 - int(tm))]["first_gank_made"], g)
        self.assertGreater(seen, 0)

    def test_guardian_times_from_objectives(self):
        guard = {(o["lane"], o["owner_team"]): o["destroyed_s"]
                 for o in matches.objectives(self.mi) if o["type"] == "Guardian"}
        for ln, teams in self.res["lanes"].items():
            for tm, d in teams.items():
                self.assertEqual(d["guardian_lost_t"], guard.get((int(ln), int(tm))) or None)
                self.assertEqual(d["guardian_taken_t"], guard.get((int(ln), 1 - int(tm))) or None)

    def test_without_demo_is_aprox(self):
        res = lanephase.lane_phase(self.mi)
        self.assertEqual(res["source"], "aprox")
        for teams in res["lanes"].values():
            for d in teams.values():
                self.assertIsNone(d["dmg_done_lane"])
                self.assertIsNone(d["dmg_taken_lane"])
                self.assertIsNone(d["dmg_taken_gank"])
                self.assertGreaterEqual(d["dmg_done"], 0)
                self.assertGreaterEqual(d["dmg_taken"], 0)
        self.assertGreater(sum(p["dmg_done"] for p in res["players"].values()), 0)

    def test_deaths_kills_before_600(self):
        ds = [d for d in matches.deaths(self.mi) if d["t"] < 600]
        for slot in self.team:
            p = self.res["players"][str(slot)]
            self.assertEqual(p["deaths"], sum(1 for d in ds if d["victim_slot"] == slot))
            self.assertEqual(p["kills"], sum(1 for d in ds if d["killer_slot"] == slot
                                             and d["killer_team"] != d["victim_team"]))

    def test_invalid_lanes(self):
        paths = lanes.load_paths()
        paths = [p for p in paths if p["lane"] != 3]
        res = lanephase.lane_phase(self.mi, self.rows, self.rules, paths=paths)
        self.assertFalse(res["valid"])
        self.assertEqual(res["lanes"], {})
        self.assertTrue(all(p["lane"] is None for p in res["players"].values()))

    def test_json_serializable(self):
        json.dumps(self.res)
        json.dumps(lanephase.lane_phase(self.mi))


if __name__ == "__main__":
    unittest.main()
