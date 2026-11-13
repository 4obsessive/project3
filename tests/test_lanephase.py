"""Fase de líneas: línea de cada jugador por posiciones y duos."""
import copy
import gzip
import json
import os
import unittest

from scouting import demo, lanes, lanephase, matches, playerstats
from scouting.minimap import load_calibration

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
        # interpolación a mano entre las muestras de 540 s y 720 s
        for p in self.mi["players"]:
            st = {s["time_stamp_s"]: s for s in p["stats"]}
            f = (600 - 540) / (720 - 540)
            for fld, key in (("player_damage", "dmg_done"), ("player_damage_taken", "dmg_taken")):
                exp = round(st[540][fld] + (st[720][fld] - st[540][fld]) * f)
                self.assertEqual(res["players"][str(p["player_slot"])][key], exp)
        p0 = next(p for p in self.mi["players"] if p["player_slot"] == 1)
        st = {s["time_stamp_s"]: s for s in p0["stats"]}
        self.assertEqual(res["players"]["1"]["dmg_done"], round(st[540]["player_damage"] + (st[720]["player_damage"] - st[540]["player_damage"]) / 3))
        self.assertLess(max(p["dmg_done"] for p in res["players"].values()), 20000)

    def test_first_gank_golden_values(self):
        g = lambda ln, tm, k: self.res["lanes"][ln][tm][k]
        self.assertEqual(g("4", "0", "first_gank_made"), {"t": 235, "attacker_slot": 1, "victim_slot": 8, "kind": "dano"})
        self.assertEqual(g("4", "1", "first_gank_made"), {"t": 250, "attacker_slot": 9, "victim_slot": 6, "kind": "dano"})
        self.assertEqual(g("1", "0", "first_gank_made"), {"t": 400, "attacker_slot": 2, "victim_slot": 7, "kind": "kill"})
        self.assertEqual(g("1", "1", "first_gank_made"), {"t": 295, "attacker_slot": 12, "victim_slot": 5, "kind": "dano"})
        self.assertEqual(g("3", "0", "first_gank_made"), {"t": 265, "attacker_slot": 3, "victim_slot": 9, "kind": "dano"})
        self.assertEqual(g("3", "1", "first_gank_made"), {"t": 265, "attacker_slot": 10, "victim_slot": 1, "kind": "dano"})
        self.assertEqual(g("1", "1", "first_gank_suffered"), g("1", "0", "first_gank_made"))

    def test_tie_prefers_kill(self):
        dano = {"t": 100, "attacker_slot": 1, "victim_slot": 2, "kind": "dano"}
        kill = {"t": 100, "attacker_slot": 3, "victim_slot": 2, "kind": "kill"}
        self.assertEqual(lanephase._better(dano, kill), kill)
        self.assertEqual(lanephase._better(kill, dano), kill)
        early = {"t": 90, "attacker_slot": 1, "victim_slot": 2, "kind": "dano"}
        self.assertEqual(lanephase._better(kill, early), early)

    def test_episodes_merge_by_gap(self):
        ev = lambda t, a, v, vl: {"t": t, "attacker_slot": a, "victim_slot": v, "vlane": vl, "kind": "dano"}
        evs = [ev(100, 1, 7, 3), ev(105, 1, 7, 3), ev(125, 1, 8, 3),   # un episodio (huecos < 30), 2 víctimas
               ev(155, 1, 7, 3),                                         # hueco 30 -> nuevo episodio
               ev(100, 1, 9, 4),                                         # otra línea -> otro episodio
               ev(101, 2, 7, 3)]                                         # otro atacante
        eps = lanephase._episodes(evs)
        self.assertEqual(len(eps), 4)
        e1 = next(e for e in eps if e["att"] == 1 and 8 in e["victims"])
        self.assertEqual(e1["victims"], {7, 8})

    def test_player_gank_counts_are_episodes(self):
        self.assertEqual(sum(1 for _ in self._timed()) > 0, True)
        self.assertLess(self.res["players"]["2"]["ganks_made"], 19)
        self.assertGreater(self.res["players"]["2"]["ganks_made"], 0)

    def test_deaths_kills_before_600(self):
        ds = [d for d in matches.deaths(self.mi) if d["t"] <= 600]
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
        self.assertIsNone(res["source"])
        for p in res["players"].values():
            self.assertIsNone(p["lane"])
            self.assertIsNone(p["ganks_made"])
            self.assertIsNone(p["ganks_suffered"])
            self.assertIsNotNone(p["dmg_done"])

    def test_json_serializable(self):
        json.dumps(self.res)
        json.dumps(lanephase.lane_phase(self.mi))

    def test_stats_dmg_without_stats_is_none(self):
        mi = copy.deepcopy(self.mi)
        mi["players"][0]["stats"] = []
        slot = mi["players"][0]["player_slot"]
        done, taken = lanephase._stats_dmg(mi)
        self.assertIsNone(done[slot])
        self.assertIsNone(taken[slot])
        self.assertIsNone(lanephase.lane_phase(mi)["players"][str(slot)]["dmg_done"])


class PlayerStats(unittest.TestCase):
    def setUp(self):
        self.mi = _mi()
        self.lp = lanephase.lane_phase(self.mi)
        self.res = playerstats.player_stats(self.mi, self.lp)
        self.by = {r["slot"]: r for r in self.res}

    def test_direct_metadata(self):
        self.assertEqual(len(self.res), len(self.mi["players"]))
        for p in self.mi["players"]:
            r = self.by[p["player_slot"]]
            for k in ("kills", "deaths", "assists", "last_hits", "denies", "net_worth", "team", "account_id", "hero_id"):
                self.assertEqual(r[k], p[k], k)
            self.assertEqual(r["lane"], self.lp["players"][str(p["player_slot"])]["lane"])
            self.assertEqual(r["ganks_made"], self.lp["players"][str(p["player_slot"])]["ganks_made"])

    def test_direct_metadata_match_109084310(self):
        with open(os.path.join(ROOT, "match_109084310.json"), encoding="utf-8") as f:
            mi = json.load(f)["match_info"]
        res = {r["slot"]: r for r in playerstats.player_stats(mi, lanephase.lane_phase(mi))}
        self.assertEqual(len(res), len(mi["players"]))
        for p in mi["players"]:
            r = res[p["player_slot"]]
            for k in ("kills", "deaths", "assists", "last_hits", "net_worth"):
                self.assertEqual(r[k], p[k], k)
        p10 = next(p for p in mi["players"] if p["player_slot"] == 10)
        self.assertEqual(res[10]["net_worth"], p10["net_worth"])
        json.dumps(list(res.values()))

    def test_cells_sum_to_events_with_position(self):
        from scouting.report import cell_of
        cal = load_calibration()
        ds = matches.deaths(self.mi)

        def inside(d, team):
            x, y = (-d["x"], -d["y"]) if team == 1 else (d["x"], d["y"])
            return cell_of(x, y, cal) is not None
        total = 0
        for r in self.res:
            s, tm = r["slot"], r["team"]
            ek = [d for d in ds if d["killer_slot"] == s and d["killer_team"] != d["victim_team"] and d["x"] is not None]
            ed = [d for d in ds if d["victim_slot"] == s and d["x"] is not None]
            self.assertEqual(sum(c[2] for c in r["kill_cells"]), sum(1 for d in ek if inside(d, tm)))
            self.assertEqual(sum(c[2] for c in r["death_cells"]), sum(1 for d in ed if inside(d, tm)))
            total += sum(c[2] for c in r["death_cells"])
        self.assertGreater(total, 0)
        # todas las posiciones de la partida caen en la cuadrícula: la suma es exactamente las kills con posición
        self.assertEqual(sum(sum(c[2] for c in r["kill_cells"]) for r in self.res),
                         sum(1 for d in ds if d["killer_slot"] is not None and d["killer_team"] != d["victim_team"] and d["x"] is not None))

    def test_economy_and_stats(self):
        eco = {e["slot"]: e for e in matches.economy(self.mi)["players"]}
        for p in self.mi["players"]:
            r, s = self.by[p["player_slot"]], p["player_slot"]
            self.assertEqual(r["nw_per_min"], eco[s]["per_min"]["net_worth"])
            self.assertEqual(r["troopers_per_min"], eco[s]["per_min"]["troopers_kills"])
            self.assertEqual(r["jungla_per_min"], eco[s]["per_min"]["jungla_kills"])
            self.assertEqual(r["sources"], eco[s]["sources"])
            self.assertEqual(r["nw_at_600"], round(matches.stat_at(p, "net_worth", 600)))
            self.assertEqual(r["player_damage"], p["stats"][-1]["player_damage"])
            self.assertEqual(r["damage_taken"], p["stats"][-1]["player_damage_taken"])
            self.assertEqual(r["kda"], round((p["kills"] + p["assists"]) / max(p["deaths"], 1), 2))

    def test_player_without_stats_gives_none(self):
        mi = copy.deepcopy(self.mi)
        mi["players"][0]["stats"] = []
        slot = mi["players"][0]["player_slot"]
        r = {x["slot"]: x for x in playerstats.player_stats(mi, lanephase.lane_phase(mi))}[slot]
        for k in ("nw_at_600", "player_damage", "damage_taken", "sources"):
            self.assertIsNone(r[k], k)

    def test_json_serializable(self):
        json.dumps(self.res)


class PayloadExtras(unittest.TestCase):
    def test_match_payload_has_lane_phase_and_players(self):
        import tempfile
        from scouting import db, server
        mi = _mi()
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(os.path.join(tmp, "t.db"))
            try:
                sin = server.match_payload_extras(con, 135801973, mi)
                self.assertEqual(sin["lane_phase"]["source"], "aprox")
                raw = _load("demo_135801973.json")["results"]
                raw["lane_damage"] = _load("demo_lane_135801973.json")["rows"]
                con.execute("INSERT INTO demo_jobs (match_id, state, raw) VALUES (?, 'done', ?)", (135801973, json.dumps(raw)))
                con.commit()
                out = server.match_payload_extras(con, 135801973, mi)
            finally:
                con.close()
        self.assertTrue(out["lane_phase"]["valid"])
        self.assertEqual(out["lane_phase"]["source"], "demo")
        self.assertEqual(len(out["player_stats"]), 12)
        self.assertEqual(len(out["lane_phase"]["players"]), 12)
        json.dumps(out)


class ReportLanes(unittest.TestCase):
    """Informe de equipo: fase de líneas por dúo y jugadores (mismos números que la vista de partida)."""
    MID = 135801973

    def setUp(self):
        from scouting import report
        self.mi = _mi()
        self.data = {"match_info": self.mi}
        self.roster = {p["account_id"] for p in self.mi["players"] if p["team"] == 1}
        self.rows = _load("demo_lane_135801973.json")["rows"]
        self.rules = _load("demo_135801973.json")["results"]["rules"]
        self.ld = {self.MID: {"rows": self.rows, "rules": self.rules}}
        self.out = report.run("T", [self.data], self.roster, None, None, None, lane_data=self.ld,
                              hero_names={})
        self.sec = {s["id"]: s for s in self.out["sections"]}
        self.lp = lanephase.lane_phase(self.mi, self.rows, self.rules)

    def test_sections_present(self):
        self.assertIn("fase_lineas", self.sec)
        self.assertIn("jugadores", self.sec)
        for s in ("fase_lineas", "jugadores"):
            self.assertNotIn("error", self.sec[s])

    def test_one_duo_per_lane_n1_and_damage_equals_match(self):
        tables = [b for b in self.sec["fase_lineas"]["blocks"] if b.get("type") == "table" and b.get("kind") == "duos"]
        self.assertEqual(len(tables), 3)
        for t in tables:
            self.assertEqual(len(t["rows"]), 1)
            r = t["rows"][0]
            self.assertEqual(r["n"], 1)
            ref = self.lp["lanes"][str(r["carril_id"])]["1"]
            self.assertEqual(r["dmg_done"], ref["dmg_done"])
            self.assertEqual(r["dmg_taken"], ref["dmg_taken"])
            self.assertEqual(r["dmg_taken_gank"], ref["dmg_taken_gank"])

    def test_players_six_with_kills(self):
        tb = next(b for b in self.sec["jugadores"]["blocks"] if b.get("kind") == "jugadores")
        self.assertEqual(len(tb["rows"]), 6)
        ps = {p["account_id"]: p for p in playerstats.player_stats(self.mi, self.lp)}
        self.assertEqual(sum(r["kills"] for r in tb["rows"]), sum(ps[a]["kills"] for a in self.roster))
        for r in tb["rows"]:
            self.assertEqual(r["lane_dmg_done"], ps[r["account_id"]]["lane_dmg_done"])

    def test_times_in_seconds_with_mmss(self):
        t = next(b for b in self.sec["fase_lineas"]["blocks"] if b.get("kind") == "duos")
        cols = {c["key"]: c for c in t["columns"]}
        self.assertEqual(cols["g_taken"]["fmt"], "mmss")
        r = t["rows"][0]
        ref = self.lp["lanes"][str(r["carril_id"])]["1"]
        self.assertEqual(r["g_taken"], ref["guardian_taken_t"])
        self.assertEqual(r["g_lost"], ref["guardian_lost_t"])

    def test_guardian_not_fallen_excluded_and_counted(self):
        from scouting import report
        mi = copy.deepcopy(self.mi)
        for o in mi["objectives"]:
            o["destroyed_time_s"] = 0
        out = report.run("T", [{"match_info": mi}], self.roster, None, None, None, lane_data=self.ld)
        sec = {s["id"]: s for s in out["sections"]}
        t = next(b for b in sec["fase_lineas"]["blocks"] if b.get("kind") == "duos")
        r = t["rows"][0]
        self.assertIn(r["g_taken"] is None or r["g_lost"] is None, (True,))
        self.assertTrue(r["g_taken_no"] == "1 de 1" or r["g_lost_no"] == "1 de 1")

    def test_names_and_heroes_populated(self):
        from scouting import report
        acc = sorted(self.roster)
        ids = {acc[0]: {"player_id": 7, "name": "Ana"}, acc[1]: {"player_id": None, "name": "Steam Bob"}}
        out = report.run("T", [self.data], self.roster, None, None, None, lane_data=self.ld, player_ids=ids,
                         hero_names={h: f"H{h}" for h in range(1, 200)})
        sec = {s["id"]: s for s in out["sections"]}
        rows = next(b for b in sec["jugadores"]["blocks"] if b.get("kind") == "jugadores")["rows"]
        names = {r["account_id"]: r["jugador"] for r in rows}
        self.assertEqual(len(rows), 6)
        self.assertEqual(names[acc[0]], "Ana")
        self.assertEqual(names[acc[1]], "Steam Bob")
        self.assertEqual(names[acc[2]], f"Cuenta {acc[2]}")
        duo = next(b for b in sec["fase_lineas"]["blocks"] if b.get("kind") == "duos")["rows"][0]["duo"]
        self.assertTrue(duo.startswith("H"))

    def test_without_demo_damage_unavailable(self):
        from scouting import report
        out = report.run("T", [self.data], self.roster)
        sec = {s["id"]: s for s in out["sections"]}
        blocks = sec["fase_lineas"]["blocks"]
        self.assertTrue(any(b.get("type") == "unavailable" for b in blocks))
        for t in (b for b in blocks if b.get("kind") == "duos"):
            self.assertIsNone(t["rows"][0]["dmg_done"])
        json.dumps(out)

    def test_json_serializable(self):
        json.dumps(self.out)

    def _mixed(self, n_demo, n_aprox):
        from scouting import report
        datas, ld = [], {}
        for i in range(n_demo + n_aprox):
            mi = copy.deepcopy(self.mi)
            mi["match_id"] = self.MID + i
            datas.append({"match_info": mi})
            if i < n_demo:
                ld[mi["match_id"]] = {"rows": self.rows, "rules": self.rules}
        out = report.run("T", datas, self.roster, None, None, None, lane_data=ld)
        self.mixed_out = out
        return {s["id"]: s for s in out["sections"]}["fase_lineas"]

    def test_gank_table_only_demo_matches(self):
        sec = self._mixed(3, 2)
        t = next(b for b in sec["blocks"] if b.get("kind") == "ganks")
        self.assertEqual(t["n"], 3)
        self.assertIn("solo partidas con demo", t["note"])
        for r in t["rows"]:
            self.assertEqual(r["n"], 3)
            ref = self.lp["lanes"][str(r["carril_id"])]["1"]
            self.assertEqual(r["suf_n"], 3 if ref["first_gank_suffered"] else 0)
            self.assertEqual(r["made_n"], 3 if ref["first_gank_made"] else 0)
        # hallazgos sobre las 3 partidas con demo, no sobre las 5
        import re
        found = re.findall(r"[Gg]ank\w* en [^.]*?en (\d+) de (\d+) partidas", json.dumps(self.mixed_out, ensure_ascii=False))
        self.assertTrue(found)
        for _, total in found:
            self.assertEqual(total, "3")

    def test_gank_table_unavailable_without_demo(self):
        sec = self._mixed(0, 2)
        self.assertFalse(any(b.get("kind") == "ganks" for b in sec["blocks"]))
        self.assertTrue(any(b.get("type") == "unavailable" and "gankeo" in b.get("title", "").lower() for b in sec["blocks"]))


class LanePhaseFallbacks(unittest.TestCase):
    """Demo incompleto (límite de tick por debajo de 600 s de juego) o sin filas utilizables → aprox, nunca ceros."""

    def setUp(self):
        self.mi = _mi()
        self.rows = _load("demo_lane_135801973.json")["rows"]
        self.rules = _load("demo_135801973.json")["results"]["rules"]
        self.aprox = lanephase.lane_phase(self.mi)

    def _same_as_aprox(self, res):
        self.assertEqual(res["source"], "aprox")
        self.assertEqual(res["players"], self.aprox["players"])
        self.assertEqual(res["lanes"], self.aprox["lanes"])

    def test_default_limit_is_legacy_48000_and_complete_here(self):
        res = lanephase.lane_phase(self.mi, self.rows, self.rules)
        self.assertEqual(res["source"], "demo")
        self.assertFalse(res["demo_incompleto"])
        self.assertEqual(lanephase.lane_phase(self.mi, self.rows, self.rules, tick_limit=48000), res)

    def test_new_limit_is_complete(self):
        res = lanephase.lane_phase(self.mi, self.rows, self.rules, tick_limit=demo.LANE_TICK_LIMIT)
        self.assertEqual(res["source"], "demo")
        self.assertFalse(res["demo_incompleto"])

    def test_limit_below_600s_is_incomplete(self):
        rules = copy.deepcopy(self.rules)
        for r in rules:
            r["paused_ticks"] = 20000  # 48000 - 20000 = 28000 ticks = 437 s < 600
        res = lanephase.lane_phase(self.mi, self.rows, rules)
        self._same_as_aprox(res)
        self.assertTrue(res["demo_incompleto"])
        res = lanephase.lane_phase(self.mi, self.rows, self.rules, tick_limit=30000)
        self._same_as_aprox(res)
        self.assertTrue(res["demo_incompleto"])

    def test_empty_rows_is_aprox(self):
        res = lanephase.lane_phase(self.mi, [], self.rules)
        self._same_as_aprox(res)
        self.assertFalse(res["demo_incompleto"])

    def test_unmapped_rows_is_aprox(self):
        rows = [dict(r, att=r["att"] + 10**9, vic=r["vic"] + 10**9) for r in self.rows]
        self._same_as_aprox(lanephase.lane_phase(self.mi, rows, self.rules))

    def test_aprox_has_no_gank_counts(self):
        # Los gankeos necesitan el demo: sin él son None («–»), no un recuento parcial de kills.
        self.assertEqual(self.aprox["source"], "aprox")
        for p in self.aprox["players"].values():
            self.assertIsNone(p["ganks_made"])
            self.assertIsNone(p["ganks_suffered"])
        for teams in self.aprox["lanes"].values():
            for d in teams.values():
                self.assertIsNone(d["first_gank_made"])
                self.assertIsNone(d["first_gank_suffered"])

    def test_payload_incomplete_demo_from_stored_limit(self):
        import tempfile
        from scouting import db, server
        raw = _load("demo_135801973.json")["results"]
        raw["lane_damage"] = self.rows
        raw["lane_damage_limit"] = 30000
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(os.path.join(tmp, "t.db"))
            try:
                con.execute("INSERT INTO demo_jobs (match_id, state, raw) VALUES (?, 'done', ?)", (135801973, json.dumps(raw)))
                con.commit()
                out = server.match_payload_extras(con, 135801973, self.mi)
            finally:
                con.close()
        self.assertEqual(out["lane_phase"]["source"], "aprox")
        self.assertTrue(out["lane_phase"]["demo_incompleto"])

    def test_report_incomplete_demo_counts_as_no_demo(self):
        from scouting import report
        roster = {p["account_id"] for p in self.mi["players"] if p["team"] == 1}
        ld = {135801973: {"rows": self.rows, "rules": self.rules, "limit": 30000}}
        out = report.run("T", [{"match_info": self.mi}], roster, None, None, None, lane_data=ld)
        sec = {s["id"]: s for s in out["sections"]}
        cov = next(b for b in sec["fase_lineas"]["blocks"] if b.get("type") == "text" and "Con demo" in b["text"])
        self.assertIn("Con demo de fase de líneas: 0 de 1", cov["text"])
        self.assertIn("incompleto", cov["text"])
        for t in (b for b in sec["fase_lineas"]["blocks"] if b.get("kind") == "duos"):
            self.assertIsNone(t["rows"][0]["dmg_done"])


if __name__ == "__main__":
    unittest.main()
