"""Servidor HTTP local: estáticos + API JSON.

Seguridad (solo uso local): escucha en 127.0.0.1, valida la cabecera Host (contra DNS rebinding),
las escrituras solo se aceptan como application/json y con Origin local si viene."""
import gzip
import json
import mimetypes
import os
import re
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import analysis, config, db, demo, images, matches, minimap, players, report, summary, updater as updater_mod
from .api import ApiError
from .db import kv_get
from .ids import to_account_id

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("font/woff2", ".woff2")

MAX_BODY = 50 * 1024 * 1024
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "frame-ancestors 'none'; base-uri 'none'")


class HttpError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


_API_IMG_PREFIX = "https://assets-bucket.deadlock-api.com/assets-api-res/images/"


def _api_image_path(url):
    """URL completa de la API de assets -> ruta del proxy local (otros hosts: None)."""
    if isinstance(url, str) and url.startswith(_API_IMG_PREFIX) and len(url) > len(_API_IMG_PREFIX):
        return "/img/api/" + url[len(_API_IMG_PREFIX):]
    return None


def _wiki_hero_file(name):
    return name.replace("&", "%26").replace(" ", "_") + "_vertical.png"


def _qint(req, name, default):
    try:
        return int(req.query.get(name, [default])[0])
    except (TypeError, ValueError):
        raise HttpError(400, f"Parámetro no válido: {name}")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


MATCH_MODES = ("ranked", "ranked,unranked")


def validate_config(changes):
    """Valida los cambios de /api/config; lanza HttpError(400) si algo no cuadra."""
    if "update_interval_hours" in changes:
        v = changes["update_interval_hours"]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not (1 <= v <= 720):
            raise HttpError(400, "update_interval_hours debe ser un número entre 1 y 720")
        changes["update_interval_hours"] = float(v)
    for k, lo, hi in (("stats_days", 1, 365), ("batch_size", 1, 1000)):
        if k in changes:
            v = changes[k]
            if not _is_int(v) or not (lo <= v <= hi):
                raise HttpError(400, f"{k} debe ser un entero entre {lo} y {hi}")
    if "extra_leaderboard_ids" in changes:
        v = changes["extra_leaderboard_ids"]
        if not isinstance(v, list) or not all(_is_int(x) for x in v):
            raise HttpError(400, "extra_leaderboard_ids debe ser una lista de enteros")
    if "stats_match_mode" in changes:
        if changes["stats_match_mode"] not in MATCH_MODES:
            raise HttpError(400, "stats_match_mode debe ser " + " o ".join(f"«{m}»" for m in MATCH_MODES))
    if "api_key" in changes:
        v = changes["api_key"]
        if not isinstance(v, str) or len(v) > 200:
            raise HttpError(400, "api_key debe ser texto de 200 caracteres como máximo")
    return changes


class App:
    def __init__(self, client, updater, port):
        self.client = client
        self.updater = updater
        self.port = port
        self.routes = []
        self._calib_lock = threading.Lock()
        r = self.route
        r("GET", r"/api/status", self.status)
        r("GET", r"/api/demo/status", self.demo_status)
        r("GET", r"/api/players", self.players_all)
        r("GET", r"/api/players/(\d+)", self.player_profile)
        r("POST", r"/api/players/(\d+)/manual", self.player_manual)
        r("POST", r"/api/players/(\d+)/link", self.player_link)
        r("POST", r"/api/players/(\d+)/unlink", self.player_unlink)
        r("POST", r"/api/players/add", self.player_add)
        r("GET", r"/api/heroes", self.heroes)
        r("GET", r"/api/climbers", self.climbers)
        r("GET", r"/api/ranks", self.ranks)
        r("GET", r"/api/teams", self.teams)
        r("POST", r"/api/teams/reload", self.teams_reload)
        r("GET", r"/api/teams/recent-matches", self.team_recent)
        r("POST", r"/api/update", self.update_now)
        r("GET", r"/api/config", self.config_get)
        r("POST", r"/api/config", self.config_set)
        r("GET", r"/api/roles", self.roles_get)
        r("POST", r"/api/roles", self.roles_set)
        r("GET", r"/api/matches", self.matches_list)
        r("POST", r"/api/matches/load", self.match_load)
        r("POST", r"/api/matches/upload", self.match_upload)
        r("GET", r"/api/matches/(\d+)", self.match_overview)
        r("GET", r"/api/matches/(\d+)/demo", self.match_demo)
        r("GET", r"/api/matches/(\d+)/positions", self.match_positions)
        r("GET", r"/api/matches/(\d+)/raw", self.match_raw)
        r("POST", r"/api/matches/(\d+)/delete", self.match_delete)
        r("GET", r"/api/objective-map", self.objmap_get)
        r("POST", r"/api/objective-map", self.objmap_set)
        r("GET", r"/api/map", self.map_info)
        r("POST", r"/api/map/calibrate", self.map_calibrate)
        r("POST", r"/api/map/calibration", self.map_calibration_save)
        r("GET", r"/api/report/metrics", self.report_metrics)
        r("POST", r"/api/report", self.report_run)
        r("POST", r"/api/import-old", self.import_old)

    def route(self, method, pattern, fn):
        self.routes.append((method, re.compile(pattern + r"$"), fn))

    def con(self):
        return db.get()

    # ---------------------------------------------------------------- estado
    def status(self, req):
        con = self.con()
        s = self.updater.snapshot()
        s["counts"] = {
            "players": con.execute("SELECT COUNT(*) FROM players").fetchone()[0],
            "accounts": con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0],
            "snapshots": con.execute("SELECT COUNT(*) FROM lb_snapshots").fetchone()[0],
            "matches": con.execute("SELECT COUNT(*) FROM matches").fetchone()[0],
        }
        s["current_leaderboard_id"] = analysis.current_lid(con)
        s["season_names"] = json.loads(kv_get(con, "season_names") or "{}")
        cfg = config.load()
        s["region"] = cfg["region"]
        s["stats_window"] = {
            "start": int(kv_get(con, "stats_window_start", 0) or 0) or None,
            "end": int(kv_get(con, "stats_window_end", 0) or 0) or None,
            "match_mode": kv_get(con, "stats_match_mode") or None,
            "days": cfg["stats_days"],
            "configured_mode": cfg.get("stats_match_mode") or "ranked",
        }
        return s

    def demo_status(self, req):
        return demo.counts(self.con())

    def update_now(self, req):
        started = self.updater.start("manual (botón)")
        return {"started": started, "message": "Actualización iniciada" if started else "Ya hay una actualización en curso"}

    # -------------------------------------------------------------- jugadores
    def players_all(self, req):
        return RawJson(summary.all_json(self.con()))

    def player_profile(self, req, pid):
        con = self.con()
        with_duos = req.query.get("duos", ["1"])[0] != "0"
        p = players.profile(con, self.client, int(pid), analysis.current_lid(con), with_duos=with_duos)
        if not p:
            raise HttpError(404, "Jugador no encontrado")
        return p

    def player_manual(self, req, pid):
        try:
            return players.update_manual(self.con(), int(pid), req.json())
        except KeyError:
            raise HttpError(404, "Jugador no encontrado")
        except ValueError as e:
            raise HttpError(400, str(e))

    def player_link(self, req, pid):
        aid = to_account_id(req.json().get("account"))
        if not aid:
            raise HttpError(400, "ID de cuenta no válido (número, [U:1:N], steam64 o URL de perfil)")
        players.link_account(self.con(), int(pid), aid)
        return players.profile(self.con(), None, int(pid), analysis.current_lid(self.con()), with_duos=False)

    def player_unlink(self, req, pid):
        aid = to_account_id(req.json().get("account"))
        try:
            new_pid = players.unlink_account(self.con(), int(pid), aid)
        except ValueError as e:
            raise HttpError(400, str(e))
        return {"ok": True, "new_player_id": new_pid}

    def player_add(self, req):
        body = req.json()
        aid = to_account_id(body.get("account"))
        if not aid:
            raise HttpError(400, "ID de cuenta no válido")
        con = self.con()
        pid = players.player_of(con, aid)
        if pid is None:
            with con:
                pid = players.create_player(con, aid, (body.get("name") or "").strip() or None, "manual")
            try:
                updater_mod.fetch_steam_profiles(con, self.client, [aid])
                cfg = config.load()
                stats = self.client.hero_stats([aid], db.now() - int(cfg["stats_days"]) * 86400,
                                               match_mode=cfg.get("stats_match_mode") or "ranked")
                with con:
                    db.insert_hero_stats(con, stats)
            except ApiError as e:
                print(f"[api] no se pudieron bajar datos de {aid}: {e}")
            summary.materialize(con, [pid])
        return {"player_id": pid}

    def heroes(self, req):
        con = self.con()
        names = json.loads(kv_get(con, "hero_names") or "{}")
        imgs = json.loads(kv_get(con, "hero_images") or "{}")
        assets = json.loads(kv_get(con, "hero_assets") or "{}")
        if not names:
            try:
                hs = self.client.heroes()
                names = {str(h["id"]): h["name"] for h in hs if h.get("player_selectable") and not h.get("disabled")}
                imgs = {str(h["id"]): (h.get("images") or {}).get("icon_image_small_webp") for h in hs}
                assets = {str(k): v for k, v in updater_mod.hero_assets(hs, {int(k) for k in names}).items()}
            except ApiError:
                pass
        out = []
        for k, v in sorted(names.items(), key=lambda kv: kv[1]):
            a = assets.get(k) or {}
            out.append({"id": int(k), "name": v, "image": _api_image_path(imgs.get(k)),
                        "wiki_image": "/img/wiki/" + _wiki_hero_file(v),
                        "card": _api_image_path(a.get("card")), "vertical": _api_image_path(a.get("vertical")),
                        "bg": _api_image_path(a.get("bg")),
                        "color": a.get("color") if isinstance(a.get("color"), str) and re.fullmatch(r"#[0-9a-f]{6}", a.get("color") or "") else None})
        return out

    def ranks(self, req):
        """Nombres e imágenes de los rangos (tier = badge // 10, subrank = badge % 10)."""
        try:
            data = self.client.rank_assets()
        except (ApiError, AttributeError):
            return []
        out = []
        for r in data or []:
            im = r.get("images") or {}
            out.append({"tier": r.get("tier"), "name": r.get("name"),
                        "color": r.get("color") if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(r.get("color") or "")) else None,
                        "image": _api_image_path(im.get("small_webp") or im.get("large_webp")),
                        "subranks": {str(i): _api_image_path(im.get(f"small_subrank{i}_webp") or im.get(f"subrank{i}_webp"))
                                     for i in range(1, 7) if im.get(f"small_subrank{i}_webp") or im.get(f"subrank{i}_webp")}})
        return out

    def climbers(self, req):
        days = _qint(req, "days", "7")
        metric = req.query.get("metric", ["rel"])[0]
        return analysis.climbers(self.con(), days, "pos" if metric == "pos" else "rel")

    # ---------------------------------------------------------------- equipos
    def teams(self, req):
        return analysis.teams_overview(self.con())

    def teams_reload(self, req):
        con = self.con()
        res = updater_mod.sync_teams(con)
        summary.materialize(con)
        return res

    def team_recent(self, req):
        team = req.query.get("team", [""])[0]
        extra = [to_account_id(x) for x in req.query.get("extra", [""])[0].split(",") if to_account_id(x)]
        minp = _qint(req, "min_players", "3")
        days = _qint(req, "days", "60")
        if not team and not extra:
            raise HttpError(400, "Falta el equipo")
        return analysis.recent_team_matches(self.con(), self.client, team, extra, minp, days)

    # ---------------------------------------------------------------- ajustes
    def config_get(self, req):
        cfg = config.load()
        cfg["api_key"] = "••••" if cfg.get("api_key") else ""
        return cfg

    def config_set(self, req):
        body = req.json()
        allowed = {"region", "extra_leaderboard_ids", "update_interval_hours", "stats_days", "batch_size", "api_key", "stats_match_mode"}
        changes = {k: v for k, v in body.items() if k in allowed}
        if changes.get("api_key") == "••••":
            changes.pop("api_key")
        if "region" in changes and changes["region"] not in ("Europe", "Asia", "NAmerica", "SAmerica", "Oceania"):
            raise HttpError(400, "Región no válida")
        validate_config(changes)
        cfg = config.update(changes)
        if "api_key" in changes:
            self.client.api_key = cfg["api_key"]
        return self.config_get(req)

    def roles_get(self, req):
        with open(config.ROLES_PATH, encoding="utf-8") as f:
            return json.load(f)

    def roles_set(self, req):
        body = req.json()
        roles = body.get("roles")
        if not isinstance(roles, dict) or not all(isinstance(v, list) for v in roles.values()):
            raise HttpError(400, "Formato: {roles: {Rol: [héroes]}}")
        with open(config.ROLES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        data["roles"] = {k.strip(): [str(h).strip() for h in v if str(h).strip()] for k, v in roles.items() if k.strip()}
        if "umbral_rol" in body:
            data["umbral_rol"] = float(body["umbral_rol"])
        with open(config.ROLES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        summary.materialize(self.con())
        return data

    # --------------------------------------------------------------- partidas
    def matches_list(self, req):
        con = self.con()
        rows = [dict(r) for r in con.execute("SELECT * FROM matches ORDER BY start_time DESC")]
        for r in rows:
            r["players"] = [dict(p) for p in con.execute("SELECT player_slot, team, account_id, hero_id FROM match_players WHERE match_id=? ORDER BY team, player_slot", (r["match_id"],))]
        return rows

    def match_load(self, req):
        mid = req.json().get("match_id")
        try:
            mid = int(str(mid).strip())
        except (TypeError, ValueError):
            raise HttpError(400, "ID de partida no válido")
        try:
            matches.fetch(self.con(), self.client, mid)
        except ApiError as e:
            raise HttpError(502 if e.status != 404 else 404, f"La API no devolvió la partida {mid}: {e}")
        return {"match_id": mid}

    def match_upload(self, req):
        try:
            mid = matches.store_raw(self.con(), req.body, "subida")
        except matches.MatchError as e:
            raise HttpError(400, str(e))
        return {"match_id": mid}

    def _hero_names(self):
        return {int(k): v for k, v in json.loads(kv_get(self.con(), "hero_names") or "{}").items()}

    def _load(self, mid):
        try:
            return matches.load(int(mid))
        except KeyError:
            raise HttpError(404, f"Partida {mid} no guardada")

    def match_overview(self, req, mid):
        d = self._load(mid)
        out = matches.overview(d["match_info"], self._hero_names())
        con = self.con()
        try:  # nombres y avatares de Steam de los 12 jugadores (caché de 7 días)
            updater_mod.fetch_steam_profiles(con, self.client, [p["account_id"] for p in out["players"]])
        except Exception as e:
            print(f"[api] sin perfiles de Steam para la partida {mid}: {e}")
        for p in out["players"]:
            r = con.execute("SELECT p.id, COALESCE(p.display_name, a.steam_name) n FROM accounts a JOIN players p ON p.id=a.player_id WHERE a.account_id=?", (p["account_id"],)).fetchone()
            sp = con.execute("SELECT personaname, avatar FROM steam_profiles WHERE account_id=?", (p["account_id"],)).fetchone()
            p["player_id"], p["name"] = (r["id"], r["n"]) if r else (None, None)
            p["steam_name"] = sp["personaname"] if sp else None
            p["avatar"] = images.steam_avatar_path(sp["avatar"]) if sp else None
            if not p["name"]:
                p["name"] = p["steam_name"]
        out.update(self._demo_of(con, mid, d["match_info"]))
        return out

    @staticmethod
    def _demo_of(con, mid, mi):
        dm = demo.summary(con, int(mid))
        return {"demo": dm, "comeback": matches.comeback_flags(mi, dm)}

    def match_demo(self, req, mid):
        """Solo el demo y las banderas de remontada: la vista lo sondea mientras está pendiente."""
        return self._demo_of(self.con(), mid, self._load(mid)["match_info"])

    def match_positions(self, req, mid):
        step = max(1, _qint(req, "step", "1"))
        return matches.decode_positions(self._load(mid)["match_info"], step)

    def match_raw(self, req, mid):
        if not matches.is_stored(int(mid)):
            raise HttpError(404, "Partida no guardada")
        return RawJson(matches.raw_gz(int(mid)), gzipped=True)

    def match_delete(self, req, mid):
        matches.delete(self.con(), int(mid))
        return {"ok": True}

    def objmap_get(self, req):
        objs, lanes = matches.load_objective_map()
        return {"objetivos": {str(k): v for k, v in objs.items()}, "carriles": {str(k): v for k, v in lanes.items()},
                "colores": matches.load_lane_colors()}

    def objmap_set(self, req):
        body = req.json()
        try:
            objs = {int(k): {"tipo": str(v["tipo"]), "carril": (int(v["carril"]) if v.get("carril") not in (None, "") else None),
                             **({"n": int(v["n"])} if v.get("n") else {})} for k, v in body["objetivos"].items()}
            lanes = {int(k): str(v) for k, v in body.get("carriles", {}).items()}
            colores = None
            if body.get("colores") is not None:
                if not isinstance(body["colores"], dict):
                    raise ValueError("colores debe ser un objeto")
                colores = {}
                for k, v in body["colores"].items():
                    if not isinstance(v, dict):
                        raise ValueError("cada color debe ser un objeto")
                    color = str(v["color"])
                    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                        raise ValueError(f"color no válido: {color}")
                    colores[int(k)] = {"color": color, "alias": str(v.get("alias", ""))}
        except (KeyError, ValueError, TypeError) as e:
            raise HttpError(400, f"Mapeo no válido: {e}")
        matches.save_objective_map(objs, lanes, colores=colores)
        return self.objmap_get(req)

    # -------------------------------------------------------------------- mapa
    def map_info(self, req):
        info = {"image": "/static/minimap.png", "calibration": minimap.load_calibration()}
        try:
            a = self.client.map_asset()
            info["objective_positions"] = a.get("objective_positions")
            info["radius"] = a.get("radius")
            styles = matches.load_lane_styles()
            by_color = {v["color"].lower(): k for k, v in matches.LANE_DEFAULTS.items()}
            lane_paths = []
            for z in a.get("zipline_paths") or []:
                ox, oy = (z.get("origin") or [0, 0])[:2]
                pts = [[ox + p[0], oy + p[1]] for p in z.get("P0_points") or []]
                lane = by_color.get(str(z.get("color", "")).lower())
                if lane is not None and pts:
                    lane_paths.append({"lane": lane, "color": (styles.get(lane) or {}).get("color") or z["color"],
                                       "points": pts})
            info["lane_paths"] = lane_paths
            info["koth"] = [[r["position"][0], r["position"][1]]
                            for r in (a.get("entities") or {}).get("unstable_rifts") or []
                            if r.get("position")]
        except ApiError:
            info["objective_positions"] = None
            info["lane_paths"] = []
            info["koth"] = []
        return info

    def map_calibrate(self, req):
        if not self._calib_lock.acquire(blocking=False):
            raise HttpError(409, "Ya hay una calibración en curso")
        try:
            con = self.con()
            ids = [r[0] for r in con.execute("SELECT match_id FROM matches ORDER BY stored_at DESC LIMIT 30")]
            if not ids:
                raise HttpError(400, "Carga al menos una partida para calibrar")
            datas = [matches.load(i) for i in ids]
            pts = minimap.alive_points(datas, step=5)
            fitted = minimap.fit(pts)
            cur = minimap.load_calibration()
            cmp = minimap.compare({"actual": cur, "oficial": minimap.OFFICIAL, "ajustada": fitted}, pts)
            return {"fitted": fitted, "compare": cmp, "matches": len(ids), "points": len(pts)}
        finally:
            self._calib_lock.release()

    def map_calibration_save(self, req):
        body = req.json()
        if body.get("official"):
            cal = dict(minimap.OFFICIAL)
        else:
            raw = body.get("calibration") or {}
            if not isinstance(raw, dict):
                raise HttpError(400, "Calibración no válida")
            cal = {}
            for k in ("x_min", "x_max", "y_min", "y_max"):
                v = raw.get(k)
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise HttpError(400, f"Falta {k}")
                cal[k] = v
            for k in ("invert_x", "invert_y"):
                if k in raw:
                    if not isinstance(raw[k], bool):
                        raise HttpError(400, f"{k} debe ser booleano")
                    cal[k] = raw[k]
            if not (cal["x_min"] < cal["x_max"] and cal["y_min"] < cal["y_max"]):
                raise HttpError(400, "Se requiere x_min < x_max e y_min < y_max")
        minimap.save_calibration(cal)
        return cal

    # ----------------------------------------------------------------- informe
    def report_metrics(self, req):
        return report.list_metrics()

    def report_run(self, req):
        body = req.json()
        team = (body.get("team") or "").strip()
        extra = [to_account_id(x) for x in body.get("extra_accounts", []) if to_account_id(x)]
        ids = []
        for x in body.get("match_ids", []):
            try:
                ids.append(int(str(x).strip()))
            except ValueError:
                raise HttpError(400, f"ID de partida no válido: {x}")
        if not ids:
            raise HttpError(400, "Indica al menos una partida")
        con = self.con()
        roster = analysis.roster(con, team, extra) if team else set(extra)
        if not roster and not body.get("side_overrides"):
            raise HttpError(400, "La plantilla está vacía: elige un equipo de equipos.txt o añade cuentas")
        datas, errors = [], []
        for mid in dict.fromkeys(ids):
            try:
                datas.append(matches.fetch(con, self.client, mid))
            except (ApiError, matches.MatchError) as e:
                errors.append({"match_id": mid, "error": str(e)})
        demo_summaries = {d["match_info"]["match_id"]: demo.summary(con, d["match_info"]["match_id"]) for d in datas}
        out = report.run(team or "Plantilla manual", datas, roster, body.get("side_overrides"), body.get("params"), demo_summaries)
        out["load_errors"] = errors
        out["roster_size"] = len(roster)
        return out

    def import_old(self, req):
        from . import importer
        path = str(req.json().get("path") or "").strip().strip('"')
        if not path or not os.path.isfile(path):
            raise HttpError(400, "No existe ese archivo")
        if not path.lower().endswith(".db"):
            raise HttpError(400, "El archivo debe tener extensión .db")
        dry = bool(req.json().get("dry_run"))
        return importer.import_db(self.con(), path, dry_run=dry)


class RawJson:
    def __init__(self, body, gzipped=False):
        self.body = body
        self.gzipped = gzipped


class Request:
    def __init__(self, handler, query, body):
        self.handler = handler
        self.query = query
        self.body = body

    def json(self):
        try:
            v = json.loads(self.body or b"{}")
        except ValueError:
            raise HttpError(400, "El cuerpo no es JSON válido")
        if not isinstance(v, dict):
            raise HttpError(400, "Se esperaba un objeto JSON")
        return v


def make_handler(app):
    allowed_hosts = {f"127.0.0.1:{app.port}", f"localhost:{app.port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    class Handler(BaseHTTPRequestHandler):
        server_version = "DeadlockScouting/1.0"
        protocol_version = "HTTP/1.1"
        timeout = 30

        def log_message(self, fmt, *args):
            pass  # silencioso; los errores se imprimen aparte

        def _send(self, status, body, ctype="application/json; charset=utf-8", gz=False, headers=None):
            compressible = ctype.startswith(("application/json", "text/"))
            if compressible and not gz and len(body) > 2048 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                body = gzip.compress(body, 5)
                gz = True
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            extra = headers or {}
            if not any(k.lower() == "cache-control" for k in extra):
                self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "no-cache")
            if gz:
                self.send_header("Content-Encoding", "gzip")
            for k, v in extra.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _error(self, status, msg):
            self._send(status, json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8"))

        def _check_host(self):
            host = (self.headers.get("Host") or "").lower()
            if host not in allowed_hosts:
                self._error(403, "Host no permitido")
                return False
            return True

        def do_GET(self):
            if not self._check_host():
                return
            u = urllib.parse.urlsplit(self.path)
            if u.path.startswith("/api/"):
                if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
                    return self._error(403, "Petición entre sitios no permitida")
                return self._api("GET", u, b"")
            if u.path.startswith("/img/"):
                if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
                    return self._error(403, "Petición entre sitios no permitida")
                return self._image(u.path)
            return self._static(u.path)

        do_HEAD = do_GET

        def do_POST(self):
            if not self._check_host():
                return
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return self._error(415, "Solo se aceptan escrituras en JSON (Content-Type: application/json)")
            origin = self.headers.get("Origin")
            if origin and origin.lower() not in allowed_origins:
                return self._error(403, "Origen no permitido")
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._error(400, "Content-Length no válido")
            if n < 0:
                return self._error(400, "Content-Length no válido")
            if n > MAX_BODY:
                return self._error(413, "Cuerpo demasiado grande")
            body = self.rfile.read(n) if n else b""
            self._api("POST", urllib.parse.urlsplit(self.path), body)

        def _api(self, method, u, body):
            for m, rx, fn in app.routes:
                if m != method:
                    continue
                mt = rx.match(u.path)
                if not mt:
                    continue
                try:
                    res = fn(Request(self, urllib.parse.parse_qs(u.query), body), *mt.groups())
                    if isinstance(res, RawJson):
                        return self._send(200, res.body, gz=res.gzipped)
                    return self._send(200, json.dumps(res, ensure_ascii=False, default=str).encode("utf-8"))
                except HttpError as e:
                    return self._error(e.status, str(e))
                except ApiError as e:
                    return self._error(502, f"Error de la API de Deadlock: {e}")
                except Exception as e:
                    traceback.print_exc()
                    print(f"[server] error en {method} {u.path}: {type(e).__name__}: {e}")
                    return self._error(500, "Error interno del servidor")
            self._error(404, "Ruta no encontrada")

        def _image(self, path):
            origin, _, rest = path[len("/img/"):].partition("/")
            res = images.get(origin, urllib.parse.unquote(rest))
            if res is None:
                return self._error(404, "Imagen no disponible")
            self._send(200, res[0], res[1], headers={"Cache-Control": "public, max-age=604800"})

        def _static(self, path):
            if path in ("/", "/index.html"):
                path = "/static/index.html"
            if not path.startswith("/static/"):
                return self._error(404, "No encontrado")
            rel = urllib.parse.unquote(path[len("/static/"):])
            fp = os.path.realpath(os.path.join(config.STATIC_DIR, rel))
            if not fp.startswith(os.path.realpath(config.STATIC_DIR) + os.sep) or not os.path.isfile(fp):
                return self._error(404, "No encontrado")
            ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript") or ctype.endswith("json"):
                ctype += "; charset=utf-8"
            with open(fp, "rb") as f:
                body = f.read()
            self._send(200, body, ctype)

    return Handler


def serve(app, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
