"""Identidad de carril (nombre + color) en datos e informe."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from scouting import config, matches, report
from scouting import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_PATH = os.path.join(ROOT, "match_109084310.json")
with open(FIXTURE_PATH, encoding="utf-8") as _f:
    FIXTURE = json.load(_f)
TEAM1_ACCOUNTS = {p["account_id"] for p in FIXTURE["match_info"]["players"] if p["team"] == 1}


class _Req:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_lane_styles_defaults_and_names(self):
        s = matches.load_lane_styles()
        self.assertEqual(s[1], {"nombre": "York", "color": "#F1CC30", "alias": "amarillo"})
        self.assertEqual(s[3], {"nombre": "Broadway", "color": "#29b1cc", "alias": "azul"})
        self.assertEqual(s[4], {"nombre": "Greenwich", "color": "#59b247", "alias": "verde"})

    def test_lane_styles_without_colores_block(self):
        with open(config.OBJECTIVES_PATH, encoding="utf-8") as f:
            d = json.load(f)
        d.pop("colores", None)
        p = os.path.join(self.tmp, "objetivos.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f)
        self.assertEqual(matches.load_lane_styles(p)[1]["color"], "#F1CC30")

    def test_objective_label_uses_lane_name(self):
        objs, lanes = matches.load_objective_map()
        self.assertEqual(matches.objective_label(1, objs, lanes), "Guardian · York")
        self.assertEqual(matches.objective_label(8, objs, lanes), "Walker · Greenwich")

    def test_overview_and_report_carry_lanes(self):
        ov = matches.overview(FIXTURE["match_info"], {})
        self.assertEqual(ov["lanes"]["3"]["nombre"], "Broadway")
        out = report.run("x", [FIXTURE], TEAM1_ACCOUNTS)
        self.assertEqual(out["lanes"]["4"]["color"], "#59b247")

    def test_no_side_words_in_lane_texts(self):
        out = report.run("x", [FIXTURE], TEAM1_ACCOUNTS)
        txt = json.dumps(out, ensure_ascii=False).lower()
        for w in ("izquierda", "(izq.)", "(der.)", "derecha", "(centro)"):
            self.assertNotIn(w, txt)

    def _post(self, body):
        p = os.path.join(self.tmp, "objetivos.json")
        shutil.copy(config.OBJECTIVES_PATH, p)
        srv = object.__new__(server.App) if hasattr(server, "App") else None
        with mock.patch.object(config, "OBJECTIVES_PATH", p):
            out = srv.objmap_set(_Req(body))
            return out, matches.load_lane_styles(p)

    def test_post_without_colores_keeps_colors(self):
        objs, lanes = matches.load_objective_map()
        body = {"objetivos": {str(k): v for k, v in objs.items()}, "carriles": {str(k): v for k, v in lanes.items()}}
        out, styles = self._post(body)
        self.assertEqual(styles[1]["color"], "#F1CC30")
        self.assertIn("colores", out)

    def test_post_with_bad_color_is_400(self):
        objs, lanes = matches.load_objective_map()
        body = {"objetivos": {str(k): v for k, v in objs.items()}, "carriles": {},
                "colores": {"1": {"color": "rojo", "alias": "x"}}}
        with self.assertRaises(server.HttpError) as cm:
            self._post(body)
        self.assertEqual(cm.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
