"""Tests con la partida real 109084310 como fixture."""
import json
import math
import os
import statistics
import unittest

from scouting import matches as M
from scouting import minimap, report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "match_109084310.json")


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class MatchFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_fixture()
        cls.mi = cls.data["match_info"]

    def test_basic_fields(self):
        self.assertEqual(self.mi["match_id"], 109084310)
        self.assertEqual(self.mi["winning_team"], 0)
        self.assertEqual(len(self.mi["players"]), 12)

    def test_decode_positions_match_death_positions(self):
        pos = M.decode_positions(self.mi)
        by_slot = {p["slot"]: p for p in pos["players"]}
        errs = []
        for e in M.deaths(self.mi):
            p = by_slot[e["victim_slot"]]
            t = e["t"]
            # la última posición viva antes de morir (en t ya puede estar aparcado)
            for tt in (t, t - 1, t - 2):
                if 0 <= tt < len(p["x"]) and p["x"][tt] is not None:
                    errs.append(math.hypot(p["x"][tt] - e["x"], p["y"][tt] - e["y"]))
                    break
        self.assertGreater(len(errs), 50)
        self.assertLess(statistics.median(errs), 400)  # HANDOFF: ~184 u de error mediano

    def test_dead_positions_are_filtered(self):
        mp = self.mi["match_paths"]
        pos = M.decode_positions(self.mi)
        for q, p in zip(sorted(mp["paths"], key=lambda q: q["player_slot"]), sorted(pos["players"], key=lambda p: p["slot"])):
            for i, h in enumerate(q["health"][: len(p["x"])]):
                if h == 0:
                    self.assertIsNone(p["x"][i])
        # ninguna posición viva fuera del mundo
        for p in pos["players"]:
            for x, y in zip(p["x"], p["y"]):
                if x is not None:
                    self.assertLess(abs(x), 11000)
                    self.assertLess(abs(y), 11000)

    def test_team0_spawns_at_bottom(self):
        cal = minimap.load_calibration()
        pos = M.decode_positions(self.mi)
        for p in pos["players"]:
            u, v = minimap.world_to_rel(cal, p["x"][5], p["y"][5])
            if p["team"] == 0:
                self.assertGreater(v, 0.9)
            else:
                self.assertLess(v, 0.1)

    def test_objective_mapping(self):
        rows = M.objectives(self.mi)
        ids = {r["objective_id"] for r in rows}
        self.assertTrue({2, 6, 13}.isdisjoint(ids), "el mapa de 3 carriles no tiene carril 2")
        by = {(r["owner_team"], r["objective_id"]): r for r in rows}
        self.assertEqual(by[(1, 0)]["type"], "Core")
        self.assertEqual(by[(1, 0)]["destroyed_s"], 2416)  # Core cae al final: gana el equipo 0
        self.assertEqual(by[(1, 0)]["destroyed_by"], 0)
        self.assertEqual(by[(0, 1)]["type"], "Guardian")
        self.assertEqual(by[(0, 1)]["lane"], 1)
        self.assertEqual(by[(0, 5)]["type"], "Walker")
        self.assertEqual(by[(1, 9)]["type"], "Titan")
        self.assertEqual(by[(0, 12)]["type"], "Base guardian")
        self.assertIsNone(by[(0, 0)]["destroyed_s"])  # el Core del ganador no cae
        # los Guardians caen antes que los Walkers del mismo carril
        for team in (0, 1):
            for lane in (1, 3, 4):
                g, w = by.get((team, lane)), by.get((team, lane + 4))
                if g and w and g["destroyed_s"] and w["destroyed_s"]:
                    self.assertLess(g["destroyed_s"], w["destroyed_s"])

    def test_midboss(self):
        mb = M.midboss(self.mi)
        self.assertEqual(len(mb), 3)
        self.assertNotIn("stolen", mb[0])
        self.assertEqual(mb[0]["t"], 1237)

    def test_networth_interpolation(self):
        p = self.mi["players"][0]
        last = p["stats"][-1]
        self.assertAlmostEqual(M.stat_at(p, "net_worth", last["time_stamp_s"]), last["net_worth"])
        a, b = p["stats"][2], p["stats"][3]
        mid = M.stat_at(p, "net_worth", (a["time_stamp_s"] + b["time_stamp_s"]) / 2)
        self.assertAlmostEqual(mid, (a["net_worth"] + b["net_worth"]) / 2, delta=1)

    def test_koth_hint(self):
        sid = M.custom_stat_id(self.mi, "Comeback Gold Koth")
        self.assertIsNotNone(sid)

    def test_overview_serializable(self):
        ov = M.overview(self.mi, {})
        json.dumps(ov)
        self.assertEqual(len(ov["players"]), 12)


class SideAndReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_fixture()
        cls.mi = cls.data["match_info"]
        cls.team1 = {p["account_id"] for p in cls.mi["players"] if p["team"] == 1}

    def test_detect_side(self):
        side, counts = report.detect_side(self.mi, set(list(self.team1)[:3]))
        self.assertEqual(side, 1)
        self.assertEqual(counts, {0: 0, 1: 3})
        side, _ = report.detect_side(self.mi, set())
        self.assertIsNone(side)

    def test_economia_blocks_sources_and_rates(self):
        out = report.run("Prueba", [self.data], self.team1)
        eco = next(s for s in out["sections"] if s["id"] == "economia")
        self.assertNotIn("error", eco)
        titles = [b.get("title", "") for b in eco["blocks"]]
        self.assertTrue(any("Almas por fuente" in t for t in titles))
        self.assertTrue(any("Ritmos por minuto" in t for t in titles))
        # valores conocidos: troopers (fuente 2) y troopers/min de la primera fase, equipo 1 (nuestro) vs equipo 0
        def team_src(tm, sid):
            return sum(next((g["gold"] for g in p["stats"][-1]["gold_sources"] if g["source"] == sid), 0)
                       for p in self.mi["players"] if p["team"] == tm)
        bars = next(b for b in eco["blocks"] if b["type"] == "bars" and "Almas por fuente" in b["title"])
        k = bars["labels"].index("Troopers")
        vals = {sr["side"]: sr["values"][k] for sr in bars["series"]}
        self.assertEqual(vals["us"], team_src(1, 2))
        self.assertEqual(vals["them"], team_src(0, 2))
        tab = next(b for b in eco["blocks"] if b["type"] == "table" and "Ritmos" in b["title"])
        row = next(r for r in tab["rows"] if r["metrica"] == "Troopers/min")
        e = M.economy(self.mi)
        self.assertEqual(row["us0"], round(e["teams"]["1"]["per_phase"][0]["troopers_kills"], 1))
        self.assertEqual(row["them0"], round(e["teams"]["0"]["per_phase"][0]["troopers_kills"], 1))
        self.assertTrue(any("n=1" in c["label"] for c in tab["columns"]))
        self.assertTrue(any(r["metrica"] == "Net worth/min" for r in tab["rows"]))

    def test_economia_unreached_phase_is_none(self):
        import copy
        short = copy.deepcopy(self.data)
        short["match_info"]["duration_s"] = 1000
        out = report.run("Prueba", [short], self.team1)
        eco = next(s for s in out["sections"] if s["id"] == "economia")
        tab = next(b for b in eco["blocks"] if b["type"] == "table" and "Ritmos" in b["title"])
        for r in tab["rows"]:
            self.assertIsNone(r["us2"])
            self.assertIsNone(r["them2"])
            self.assertIsNotNone(r["us0"])
        self.assertTrue(any("n=0" in c["label"] for c in tab["columns"]))

    def test_report_runs_all_metrics(self):
        out = report.run("Prueba", [self.data], self.team1)
        self.assertEqual(out["n"], 1)
        ids = [s["id"] for s in out["sections"]]
        for needed in ("resumen", "mapa", "carriles", "midboss", "koth", "conclusiones"):
            self.assertIn(needed, ids)
        self.assertEqual(ids[-1], "conclusiones")
        for s in out["sections"]:
            self.assertNotIn("error", s, f"la métrica {s['id']} falló: {s.get('error')}")
            for b in s["blocks"]:
                self.assertIn(b["type"], {"text", "table", "bars", "histogram", "timeline", "map", "unavailable"})
        json.dumps(out)
        # muestra pequeña -> aviso
        resumen = next(s for s in out["sections"] if s["id"] == "resumen")
        self.assertTrue(any(b["type"] == "text" and b["tone"] == "warning" for b in resumen["blocks"]))
        # KOTH y cristales: no disponibles
        koth = next(s for s in out["sections"] if s["id"] == "koth")
        self.assertTrue(any(b["type"] == "unavailable" for b in koth["blocks"]))

    def test_report_has_no_interpretation(self):
        out = report.run("Prueba", [self.data], self.team1)
        for s in out["sections"]:
            for b in s["blocks"]:
                if b["type"] == "text":
                    self.assertNotEqual(b["tone"], "interpretation")
                if b["type"] == "table":
                    keys = {c["key"] for c in b["columns"]}
                    self.assertNotIn("contexto", keys)
                    self.assertNotIn("robos", keys)
                    self.assertNotIn("tipo", keys)
                    for r in b["rows"]:
                        self.assertNotEqual(r.get("tipo"), "interpretación")

        concl = next(s for s in out["sections"] if s["id"] == "conclusiones")
        texts = " ".join(str(r.get("texto", "")) for b in concl["blocks"] if b["type"] == "table" for r in b["rows"])
        for frag in ("Revisar el posicionamiento", "Reforzar el", "descuidado"):
            self.assertNotIn(frag, texts)

    def test_our_heroes(self):
        out = report.run("Prueba", [self.data], self.team1)
        heroes = out["our_heroes"]
        self.assertEqual(len(heroes), 6)
        self.assertTrue(all(h["matches"] == 1 for h in heroes))
        expected = {p["hero_id"] for p in self.mi["players"] if p["team"] == 1}
        self.assertEqual({h["hero_id"] for h in heroes}, expected)
        json.dumps(heroes)

    def test_carriles_by_lane_id(self):
        out = report.run("Prueba", [self.data], self.team1)
        blocks = next(s for s in out["sections"] if s["id"] == "carriles")["blocks"]
        names = {int(k): v["nombre"] for k, v in out["lanes"].items()}
        bars = next(b for b in blocks if b["type"] == "bars")
        self.assertEqual([names[i] for i in bars["lane_ids"]], bars["labels"])
        tiempos = next(b for b in blocks if b.get("title") == "Tiempos por carril")
        self.assertEqual(next(c for c in tiempos["columns"] if c["key"] == "carril")["fmt"], "lane")
        for r in tiempos["rows"]:
            self.assertIn(r["carril_id"], (1, 3, 4))
            self.assertEqual(names[r["carril_id"]], r["carril"])
        seqs = [b for b in blocks if b["type"] == "table" and b["columns"][0]["key"] == "orden"]
        self.assertEqual(len(seqs), 2)
        for b in seqs:
            self.assertEqual(b["columns"][0]["fmt"], "lane_seq")
            self.assertNotIn("note", b)
            for r in b["rows"]:
                self.assertIsInstance(r["orden"], list)
                for step in r["orden"]:
                    self.assertIn(step["tipo"], ("Guardian", "Walker"))
                    self.assertIn(step["carril"], (1, 3, 4))
        json.dumps(blocks)

    def test_normalization_rotates_team1(self):
        out = report.run("Prueba", [self.data], self.team1, params={"normalize": True})
        mapa = next(s for s in out["sections"] if s["id"] == "mapa")
        layer = mapa["blocks"][2]["layers"][1]  # muertes
        raw = [e for e in M.deaths(self.mi) if e["victim_team"] == 1]
        self.assertEqual(len(layer["points"]), len(raw))
        self.assertEqual(layer["points"][0][0], round(-raw[0]["x"]))

    def test_side_override_and_skip(self):
        out = report.run("Prueba", [self.data], set())
        self.assertEqual(out["n"], 0)
        self.assertEqual(len(out["skipped"]), 1)
        out = report.run("Prueba", [self.data], set(), side_overrides={109084310: 0})
        self.assertEqual(out["n"], 1)
        self.assertEqual(out["sides"][0]["source"], "manual")

    def test_failing_metric_only_breaks_its_section(self):
        def boom(ctx):
            raise RuntimeError("fallo a propósito")
        report._load_all()
        report.METRICS.append({"id": "boom", "title": "Boom", "order": 500, "fn": boom})
        try:
            out = report.run("Prueba", [self.data], self.team1)
            boom_s = next(s for s in out["sections"] if s["id"] == "boom")
            self.assertIn("fallo a propósito", boom_s["error"])
            self.assertTrue(all("error" not in s for s in out["sections"] if s["id"] != "boom"))
        finally:
            report.METRICS[:] = [m for m in report.METRICS if m["id"] != "boom"]


class Minimap(unittest.TestCase):
    def test_png_and_official_calibration(self):
        w, h, alpha = minimap.read_png_alpha(minimap.IMAGE_PNG)
        self.assertEqual((w, h), (1024, 1024))
        pts = minimap.alive_points([load_fixture()], step=10)
        res = minimap.compare({"oficial": minimap.OFFICIAL}, pts)
        self.assertGreater(res["oficial"]["precision"], 0.95)



class Economy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mi = load_fixture()["match_info"]
        cls.eco = M.economy(cls.mi)
        cls.p10 = next(p for p in cls.eco["players"] if p["slot"] == 10)

    def test_sources_sum_final(self):
        self.assertEqual(self.p10["sources"], {1: 2779, 2: 8631, 3: 2917, 4: 3518, 5: 931, 6: 2827, 7: 271, 8: 286, 12: 4347})

    def test_per_min(self):
        mins = 2416 / 60
        self.assertEqual(self.p10["per_min"]["troopers_kills"], round(70 / mins, 2))
        self.assertEqual(self.p10["per_min"]["jungla_kills"], round(8 / mins, 2))

    def test_phases_cover_duration(self):
        self.assertEqual(self.eco["phases"][-1][1], self.mi["duration_s"])
        for t in self.eco["teams"].values():
            self.assertEqual(len(t["per_phase"]), 3)
            for ph in t["per_phase"]:
                self.assertTrue(all(v >= 0 for v in ph.values()))

    def test_overview_and_names(self):
        ov = M.overview(self.mi)
        self.assertIn("economy", ov)
        self.assertEqual(ov["economy"]["source_names"][3], "Jungla")

    def test_unreached_phase_rates_are_none(self):
        import copy
        mi = copy.deepcopy(self.mi)
        mi["duration_s"] = 1000
        eco = M.economy(mi)
        self.assertEqual(eco["phases"][2], [1200, 1000])
        for t in eco["teams"].values():
            self.assertTrue(all(v is None for v in t["per_phase"][2].values()))
            self.assertTrue(all(v is not None for v in t["per_phase"][1].values()))

    def test_comeback_flags(self):
        self.assertIsNone(M.comeback_flags(self.mi, {"state": "pending"}))
        demo = {"state": "done", "midboss": [{"t": 1198}, {"t": 1500}], "koth": [{"start_t": 740}]}
        fl = M.comeback_flags(self.mi, demo)
        self.assertEqual(len(fl["midboss"]), 2)
        self.assertEqual(fl["midboss"][0], M.comeback_team_at(self.mi, 1198))
        self.assertEqual(fl["koth"], [M.comeback_team_at(self.mi, 740)])
        self.assertTrue(all(v in (None, 0, 1) for v in fl["midboss"] + fl["koth"]))


if __name__ == "__main__":
    unittest.main()
