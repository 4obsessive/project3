"""Tests de scouting sin red: IDs, equipos.txt, roles, base de datos y actualizador con cliente falso."""
import json
import os
import shutil
import tempfile
import time
import unittest

from scouting import analysis, db, players, roles, summary, teams, updater
from scouting.ids import STEAM64_BASE, steam_profile_url, to_account_id


class Ids(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(to_account_id("35187362"), 35187362)
        self.assertEqual(to_account_id("[U:1:35187362]"), 35187362)
        self.assertEqual(to_account_id("U:1:35187362"), 35187362)
        self.assertEqual(to_account_id(str(35187362 + STEAM64_BASE)), 35187362)
        self.assertEqual(to_account_id("https://steamcommunity.com/profiles/76561198036275094/"), 76009366)
        self.assertEqual(to_account_id("https://steamcommunity.com/profiles/[U:1:35187362]"), 35187362)
        self.assertIsNone(to_account_id("100"))
        self.assertIsNone(to_account_id("Thieves"))
        self.assertEqual(steam_profile_url(5), "https://steamcommunity.com/profiles/[U:1:5]")


class TeamsFile(unittest.TestCase):
    def test_parse(self):
        rows, errors = teams.parse_text(
            "# comentario\n35187362 Buff Enjoyers\n483770846, 802747733 Buff Enjoyers\n"
            "12345678 100 Thieves\n[U:1:999999] Otro\nbasura\n"
        )
        self.assertEqual(rows[0], ([35187362], "Buff Enjoyers"))
        self.assertEqual(rows[1], ([483770846, 802747733], "Buff Enjoyers"))
        self.assertEqual(rows[2], ([12345678], "100 Thieves"))
        self.assertEqual(rows[3], ([999999], "Otro"))
        self.assertEqual(len(errors), 1)


class Roles(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(roles.normalize("The Doorman"), roles.normalize("doorman"))
        self.assertEqual(roles.normalize("Mo & Krill"), roles.normalize("mo and krill"))

    def test_player_roles(self):
        table, thr = roles.load_table()
        names = {1: "Mo & Krill", 2: "Bebop", 3: "Wraith"}
        rbh = roles.hero_roles(table, names)
        self.assertEqual(sorted(rbh[1]), ["Catcher", "Frontline", "Support"])
        main, br = roles.player_roles({2: 30, 3: 1}, rbh, thr)
        self.assertEqual(main, ["Catcher"])
        self.assertIn("catcher 97%", roles.breakdown_text(br))
        # Mo & Krill reparte sus partidas en tres roles: ninguno llega al 25 % si hay otro principal
        main, br = roles.player_roles({1: 3, 3: 9}, rbh, thr)
        self.assertEqual(main, ["Carry"])


# ------------------------------------------------------------------ cliente falso
class FakeClient:
    def __init__(self):
        self.calls = []
        self.modes = []
        self.windows = []
        self.fail_stats_after = None

    def ranked_seasons(self):
        now = int(time.time())
        return [{"name": "S1", "intervals": [{"start_timestamp": now - 100 * 86400, "end_timestamp": now - 86400, "leaderboard_id": 1001}]},
                {"name": "S2", "intervals": [{"start_timestamp": now - 86400, "end_timestamp": now + 86400, "leaderboard_id": 1002}]}]

    def heroes(self):
        return [{"id": 15, "name": "Bebop", "player_selectable": True, "disabled": False, "images": {}},
                {"id": 7, "name": "Wraith", "player_selectable": True, "disabled": False, "images": {}}]

    def leaderboard(self, region, lid=None):
        self.calls.append(("lb", lid))
        if lid == 1002:
            return [{"account_name": "Alfa", "possible_account_ids": [111111, 222222], "rank": 1, "top_hero_ids": [15]},
                    {"account_name": "Beta", "possible_account_ids": [333333], "rank": 2, "top_hero_ids": []},
                    {"account_name": "Nadie", "possible_account_ids": [], "rank": 3, "top_hero_ids": []}]
        return [{"account_name": "Beta", "possible_account_ids": [333333], "rank": 5, "top_hero_ids": []},
                {"account_name": "Gamma", "possible_account_ids": [444444, 555555], "rank": 9, "top_hero_ids": []}]

    def ranks(self, ids):
        b = {111111: 20, 222222: 105, 444444: 90, 555555: 90}
        return [{"account_id": a, "badge": b.get(a, 0), "last_match": {"player_rank_final_flat_progress": 1000 + b.get(a, 0)}} for a in ids]

    def steam(self, ids):
        names = {444444: ("Otro", 5), 555555: ("Gamma", 50), 666666: ("Libre", 3), 777777: ("Libre2", 1)}
        return [{"account_id": a, "personaname": names.get(a, ("x", 0))[0], "matches_played_last_30d": names.get(a, ("x", 0))[1]} for a in ids]

    def hero_stats(self, ids, min_ts, match_mode=None):
        self.modes.append(match_mode)
        if min_ts > time.time() - 8 * 86400:  # llamada de forma reciente (7 días)
            self.calls.append(("stats7", tuple(ids)))
            return [{"account_id": a, "hero_id": 15, "matches_played": 5, "wins": 4} for a in ids]
        self.windows.append(min_ts)
        self.calls.append(("stats", tuple(ids)))
        if self.fail_stats_after is not None:
            if self.fail_stats_after <= 0:
                raise RuntimeError("corte simulado")
            self.fail_stats_after -= 1
        out = []
        for a in ids:
            out.append({"account_id": a, "hero_id": 15, "matches_played": 30, "wins": 18, "kills": 90, "deaths": 60, "assists": 300,
                        "total_player_damage": 600000, "time_played": 30 * 1800, "last_played": 1, "obj_damage_per_min": 100})
            out.append({"account_id": a, "hero_id": 7, "matches_played": 2, "wins": 1, "kills": 20, "deaths": 5, "assists": 5,
                        "total_player_damage": 60000, "time_played": 2 * 1800, "last_played": 1, "obj_damage_per_min": 300})
        return out


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "t.db")
        self.con = db.connect(self.path)
        self.teams = os.path.join(self.tmp, "equipos.txt")
        with open(self.teams, "w", encoding="utf-8") as f:
            f.write("222222 Buff Enjoyers\n666666, 777777 Buff Enjoyers\n555555 100 Thieves\n")
        self._orig = updater.config.TEAMS_PATH
        updater.config.TEAMS_PATH = self.teams
        self._cfg_load = updater.config.load
        updater.config.load = lambda: dict(updater.config.DEFAULTS, extra_leaderboard_ids=[1001], batch_size=2)

    def tearDown(self):
        updater.config.TEAMS_PATH = self._orig
        updater.config.load = self._cfg_load
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_update(self, client):
        u = updater.Updater(client, db_path=self.path)
        u.con = lambda: self.con
        u._run_safe("test")
        return u

    def test_full_update(self):
        c = FakeClient()
        u = self.run_update(c)
        self.assertIsNone(u.status["error"])
        con = self.con
        # Alfa: badge 105 gana a 20
        self.assertEqual(con.execute("SELECT account_id FROM lb_resolution WHERE name='Alfa'").fetchone()[0], 222222)
        # Gamma: empate de badge -> nombre de Steam coincide
        self.assertEqual(con.execute("SELECT account_id FROM lb_resolution WHERE name='Gamma'").fetchone()[0], 555555)
        data = json.loads(summary.all_json(con))
        by = {p["name"]: p for p in data}
        self.assertEqual(by["Alfa"]["team"], "Buff Enjoyers")
        self.assertEqual(by["Gamma"]["team"], "100 Thieves")
        self.assertEqual(by["Alfa"]["rank"], 1)
        self.assertEqual(by["Beta"]["ranks"], {"1002": 2, "1001": 5})
        self.assertIsNone(by["Beta"]["team"])
        self.assertEqual(by["Alfa"]["stats"]["matches"], 32)
        self.assertEqual(by["Alfa"]["roles"], ["Catcher"])
        # 32 partidas: un intervalo de ±17pp no es fiabilidad «Alta»
        self.assertEqual(by["Alfa"]["reliability"], "Low")
        # jugador de equipo fuera de la leaderboard: dos cuentas en la misma línea = un jugador, stats sumadas
        libre = by["Libre"]
        self.assertEqual(len(libre["accounts"]), 2)
        self.assertEqual(libre["stats"]["matches"], 64)
        # historial para tendencias
        self.assertGreater(con.execute("SELECT COUNT(*) FROM stats_history").fetchone()[0], 0)

    def test_manual_fields_survive_updates(self):
        self.run_update(FakeClient())
        pid = players.player_of(self.con, 333333)
        players.update_manual(self.con, pid, {"twitter": "@beta", "status": "contactado", "adult": "sí", "notes": "hablar el lunes"})
        with self.assertRaises(ValueError):
            players.update_manual(self.con, pid, {"adult": "17"})
        self.con.execute("DELETE FROM kv WHERE key='last_success'")
        self.run_update(FakeClient())
        s = summary.get_one(self.con, pid)
        self.assertEqual(s["manual"]["twitter"], "@beta")
        self.assertEqual(s["manual"]["status"], "contactado")
        self.assertEqual(s["manual"]["adult"], "sí")
        # el equipo manual manda sobre equipos.txt
        players.update_manual(self.con, pid, {"team": "Mi equipo"})
        self.assertEqual(summary.get_one(self.con, pid)["team"], "Mi equipo")

    def test_resume_after_failure(self):
        c = FakeClient()
        c.fail_stats_after = 1  # el segundo lote falla
        u = self.run_update(c)
        self.assertIsNotNone(u.status["error"])
        job = self.con.execute("SELECT * FROM jobs ORDER BY id DESC").fetchone()
        self.assertEqual(job["state"], "interrupted")
        self.assertEqual(job["step"], "stats")
        first_batch = c.calls[[k for k, _ in c.calls].index("stats")][1]
        c2 = FakeClient()
        u2 = self.run_update(c2)
        self.assertIsNone(u2.status["error"])
        stats_calls = [ids for k, ids in c2.calls if k == "stats"]
        # no se vuelve a pedir el lote ya descargado y no se repite la leaderboard
        self.assertFalse(any(set(first_batch) & set(ids) for ids in stats_calls))
        self.assertFalse(any(k == "lb" for k, _ in c2.calls))
        self.assertEqual(self.con.execute("SELECT state FROM jobs ORDER BY id DESC").fetchone()[0], "done")

    def test_link_and_merge(self):
        self.run_update(FakeClient())
        a = players.player_of(self.con, 333333)
        b = players.player_of(self.con, 222222)
        players.update_manual(self.con, b, {"notes": "nota B"})
        players.link_account(self.con, a, 222222)
        self.assertEqual(players.player_of(self.con, 222222), a)
        s = summary.get_one(self.con, a)
        self.assertEqual(len(s["accounts"]), 2)
        self.assertEqual(s["stats"]["matches"], 64)
        self.assertEqual(s["manual"]["notes"], "nota B")
        new = players.unlink_account(self.con, a, 222222)
        self.assertNotEqual(new, a)

    def test_climbers(self):
        con = self.con
        db.kv_set(con, "current_leaderboard_id", 1002)
        now = int(time.time())
        p = [players.create_player(con, 10000 + i, f"P{i}", "leaderboard") for i in range(4)]
        out = analysis.climbers(con, 7)
        self.assertIsNotNone(out["warning"])
        for t, order in ((now - 8 * 86400, [0, 1, 2]), (now, [2, 0, 1, 3])):
            sid = con.execute("INSERT INTO lb_snapshots(leaderboard_id, region, taken_at, n_entries) VALUES(1002,'Europe',?,?)", (t, len(order))).lastrowid
            for rank, i in enumerate(order, 1):
                con.execute("INSERT INTO lb_entries(snapshot_id, rank, player_id) VALUES(?,?,?)", (sid, rank, p[i]))
        out = analysis.climbers(con, 7)
        self.assertIsNone(out["warning"])
        self.assertEqual([c["player_id"] for c in out["climbers"]], [p[2]])
        self.assertEqual(out["climbers"][0]["delta"], 2)
        self.assertEqual([n["player_id"] for n in out["new"]], [p[3]])
        out = analysis.climbers(con, 30)
        self.assertIn("8.0 days", out["warning"])


if __name__ == "__main__":
    unittest.main()
