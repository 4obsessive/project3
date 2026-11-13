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
