"""Informe en inglés y bloques visuales (tarjetas, retratos, mini barras, iconos de objetivo)."""
import copy
import gzip
import json
import os
import re
import unittest

from scouting import demo, report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "tests", "fixtures")
MID = 135801973
SPANISH = re.compile(r"\b(partida|muerte|carril|l[ií]nea|equipo|jugador|daño|no disponible|rival|minuto)", re.I)
# claves que no son texto para el usuario (identificadores, formatos, lados)
NOT_TEXT = {"type", "tone", "kind", "fmt", "key", "side", "id", "ids", "fight"}


def _load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


def _texts(node, out, key=None):
    if isinstance(node, str):
        if key not in NOT_TEXT:
            out.append(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            _texts(v, out, k)
    elif isinstance(node, list):
        for v in node:
            _texts(v, out, key)
    return out


class ReportEnglish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(os.path.join(FX, "match_135801973.json.gz"), "rt", encoding="utf-8") as f:
            mi = json.load(f)["match_info"]
        res = _load("demo_135801973.json")["results"]
        summ = dict(demo.summarize(res), state="done")
        rows, rules = _load("demo_lane_135801973.json")["rows"], res["rules"]
        roster = {p["account_id"] for p in mi["players"] if p["team"] == 1}
        datas, ld, sm = [], {}, {}
        for i in range(3):  # 3 partidas para que salgan hallazgos
            m = copy.deepcopy(mi)
            m["match_id"] = MID + i
            datas.append({"match_info": m})
            ld[m["match_id"]] = {"rows": rows, "rules": rules}
            sm[m["match_id"]] = summ
        heroes = {h: f"Hero{h}" for h in range(1, 200)}
        cls.with_demo = report.run("T", datas, roster, demo_summaries=sm, lane_data=ld, hero_names=heroes)
        cls.without_demo = report.run("T", datas[:1], roster, hero_names=heroes)
        cls.no_side = report.run("T", datas[:1], set())

    def test_no_spanish_leftovers(self):
        for out in (self.with_demo, self.without_demo, self.no_side):
            for s in out["sections"]:
                self.assertNotIn("error", s, s.get("error"))
                for t in _texts(s, []):
                    self.assertIsNone(SPANISH.search(t), f"{s['id']}: {t!r}")
            for sk in out["skipped"]:
                self.assertIsNone(SPANISH.search(sk["reason"]), sk["reason"])

    def sec(self, sid, out=None):
        return next(s for s in (out or self.with_demo)["sections"] if s["id"] == sid)

    def test_duo_cards_match_tables(self):
        blocks = self.sec("fase_lineas")["blocks"]
        cards = next(b for b in blocks if b.get("kind") == "duo_cards")["items"]
        tables = [b for b in blocks if b.get("kind") == "duos"]
        self.assertEqual(len(cards), len(tables))
        for c in cards:
            tab = next(t for t in tables if t["rows"][0]["carril_id"] == c["lane"])
            best = max(r["dmg_done"] for r in tab["rows"] if r["dmg_done"] is not None)
            self.assertEqual(c["value"], best)
            row = next(r for r in tab["rows"] if r["dmg_done"] == best)
            self.assertEqual(c["hero_ids"], row["hero_ids"])
            self.assertEqual(c["n"], row["n_demo"])
            self.assertEqual(len(row["hero_ids"]), 2)
        cols = {c["key"]: c for c in tables[0]["columns"]}
        self.assertEqual(cols["duo"]["fmt"], "heroes")
        self.assertTrue(cols["dmg_done"]["bar"])
        self.assertEqual(cols["g_taken"]["objective"], "Guardian")

    def test_gank_card_is_max_suffered(self):
        blocks = self.sec("fase_lineas")["blocks"]
        tab = next(b for b in blocks if b.get("kind") == "ganks")
        best = max(r["suf_n"] for r in tab["rows"])
        cards = next((b for b in blocks if b.get("kind") == "gank_cards"), None)
        if not best:
            self.assertIsNone(cards)
            return
        lanes = {r["carril_id"] for r in tab["rows"] if r["suf_n"] == best}
        self.assertEqual({c["lane"] for c in cards["items"]}, lanes)
        for c in cards["items"]:
            self.assertEqual(c["value"], best)
            self.assertEqual(c["n"], next(r["n"] for r in tab["rows"] if r["carril_id"] == c["lane"]))

    def test_player_card_is_max_kills(self):
        blocks = self.sec("jugadores")["blocks"]
        tab = next(b for b in blocks if b.get("kind") == "jugadores")
        best = max(r["kills"] for r in tab["rows"] if r["kills"] is not None)
        cards = next(b for b in blocks if b.get("kind") == "player_cards")["items"]
        self.assertTrue(cards)
        for c in cards:
            row = next(r for r in tab["rows"] if r["jugador"] == c["sub"])
            self.assertEqual(c["value"], best)
            self.assertEqual(c["n"], row["n"])
            self.assertEqual(c["hero_ids"], row["hero_ids"])
        self.assertEqual(next(c for c in tab["columns"] if c["key"] == "heroes")["fmt"], "heroes")

    def test_evidence_levels_in_english(self):
        concl = self.sec("conclusiones")
        levels = {r["fuerza"] for b in concl["blocks"] if b["type"] == "table" for r in b["rows"]}
        self.assertTrue(levels <= {"", "strong", "moderate", "hint"}, levels)


if __name__ == "__main__":
    unittest.main()
