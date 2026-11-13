"""Fase de líneas: línea de cada jugador por posiciones y duos."""
import copy
import gzip
import json
import os
import unittest

from scouting import lanes

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


if __name__ == "__main__":
    unittest.main()
