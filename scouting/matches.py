"""Partidas: guardado comprimido, extracción de objetivos, Midboss, muertes y posiciones decodificadas."""
import bisect
import gzip
import json
import os
import threading
from collections import OrderedDict

from . import config
from .db import now

MATCH_DIR = os.path.join(config.DATA_DIR, "matches")

# Equipo 0 = base abajo en el minimapa (verificado: spawn y /v1/assets/map team0_core).
# Que el 0 sea Hidden King (distrito "amber") y el 1 Archmother ("sapphire") viene de fuentes de
# terceros; la API no lo dice explícitamente. Se muestra con esa advertencia.
TEAM_NAMES = {0: "Hidden King", 1: "Archmother"}
TEAM_NAMES_VERIFIED = False

_cache = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 40


# Ganchos fn(con, match_id) que se llaman al guardar una partida (p. ej. la cola del demo).
ON_STORE = []


class MatchError(ValueError):
    pass


def path_for(match_id):
    return os.path.join(MATCH_DIR, f"{int(match_id)}.json.gz")


def parse(raw):
    try:
        d = json.loads(raw)
    except ValueError as e:
        raise MatchError(f"El archivo no es JSON válido: {e}")
    if isinstance(d, dict) and "match_info" not in d and "players" in d and "match_id" in d:
        d = {"match_info": d}
    if not isinstance(d, dict) or not isinstance(d.get("match_info"), dict) or "match_id" not in d["match_info"]:
        raise MatchError("No parece una partida de deadlock-api (falta match_info.match_id)")
    return d


def store(con, data, source):
    """Guarda una partida ya parseada. Devuelve match_id."""
    mi = data["match_info"]
    mid = int(mi["match_id"])
    os.makedirs(MATCH_DIR, exist_ok=True)
    tmp = path_for(mid) + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, path_for(mid))
    with con:
        con.execute(
            "INSERT OR REPLACE INTO matches VALUES(?,?,?,?,?,?,?,?)",
            (mid, mi.get("start_time"), mi.get("duration_s"), mi.get("winning_team"), mi.get("game_mode"), mi.get("match_mode"), source, now()),
        )
        con.execute("DELETE FROM match_players WHERE match_id=?", (mid,))
        for p in mi.get("players") or []:
            con.execute(
                "INSERT INTO match_players VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, p.get("player_slot"), p.get("team"), p.get("account_id"), p.get("hero_id"), p.get("kills"), p.get("deaths"),
                 p.get("assists"), p.get("net_worth"), p.get("last_hits"), p.get("denies"), p.get("level")),
            )
    with _cache_lock:
        _cache[mid] = data
        _cache.move_to_end(mid)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    for fn in list(ON_STORE):
        try:
            fn(con, mid)
        except Exception as e:  # un gancho nunca debe impedir guardar la partida
            print(f"[partidas] gancho {getattr(fn, '__name__', fn)} falló para {mid}: {e}")
    return mid


def store_raw(con, raw, source):
    return store(con, parse(raw), source)


def is_stored(match_id):
    return os.path.exists(path_for(match_id))


def load(match_id):
    mid = int(match_id)
    with _cache_lock:
        if mid in _cache:
            _cache.move_to_end(mid)
            return _cache[mid]
    fp = path_for(mid)
    if not os.path.exists(fp):
        raise KeyError(mid)
    with gzip.open(fp, "rt", encoding="utf-8") as f:
        data = json.load(f)
    with _cache_lock:
        _cache[mid] = data
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return data


def raw_gz(match_id):
    with open(path_for(match_id), "rb") as f:
        return f.read()


def fetch(con, client, match_id):
    """Devuelve la partida, descargándola de la API si no está guardada."""
    if is_stored(match_id):
        return load(match_id)
    raw = client.match_metadata_raw(match_id)
    data = parse(raw)
    store(con, data, "api")
    return data


def delete(con, match_id):
    with con:
        con.execute("DELETE FROM matches WHERE match_id=?", (match_id,))
        con.execute("DELETE FROM match_players WHERE match_id=?", (match_id,))
    with _cache_lock:
        _cache.pop(int(match_id), None)
    if is_stored(match_id):
        os.remove(path_for(match_id))


# ------------------------------------------------------------- mapeos
def load_objective_map(path=None):
    path = path or config.OBJECTIVES_PATH
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    lanes = {int(k): v for k, v in d.get("carriles", {}).items()}
    objs = {int(k): v for k, v in d["objetivos"].items()}
    return objs, lanes


LANE_DEFAULTS = {
    1: {"nombre": "York", "color": "#F1CC30", "alias": "amarillo"},
    3: {"nombre": "Broadway", "color": "#29b1cc", "alias": "azul"},
    4: {"nombre": "Greenwich", "color": "#59b247", "alias": "verde"},
}


def load_lane_styles(path=None):
    """Carril -> {nombre, color, alias}. Siempre incluye 1, 3 y 4; el archivo sobrescribe los defaults."""
    path = path or config.OBJECTIVES_PATH
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    names = {int(k): v for k, v in d.get("carriles", {}).items()}
    raw = d.get("colores")
    colores = {int(k): v for k, v in (raw if isinstance(raw, dict) else {}).items() if isinstance(v, dict)}
    out = {k: dict(v) for k, v in LANE_DEFAULTS.items()}
    for k in set(names) | set(colores):
        st = out.setdefault(k, {"nombre": f"Carril {k}", "color": "#888888", "alias": ""})
        if k in names:
            st["nombre"] = names[k]
        c = colores.get(k) or {}
        if c.get("color"):
            st["color"] = c["color"]
        if "alias" in c:
            st["alias"] = c["alias"]
    return out


def lanes_payload(path=None):
    return {str(k): v for k, v in sorted(load_lane_styles(path).items())}


def load_lane_colors(path=None):
    """Bloque `colores` tal cual está en el archivo (clave str)."""
    path = path or config.OBJECTIVES_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("colores") or {}


def save_objective_map(objs, lanes, path=None, colores=None):
    path = path or config.OBJECTIVES_PATH
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if colores is not None:
        d["colores"] = {str(k): v for k, v in sorted(colores.items())}
    d["objetivos"] = {str(k): v for k, v in sorted(objs.items())}
    d["carriles"] = {str(k): v for k, v in sorted(lanes.items())}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def objective_label(oid, objs, lanes):
    o = objs.get(oid)
    if not o:
        return f"Objetivo #{oid}"
    if o.get("carril"):
        return f"{o['tipo']} · {lanes.get(o['carril'], 'Carril ' + str(o['carril']))}"
    if o.get("n"):
        return f"{o['tipo']} {o['n']}"
    return o["tipo"]


# --------------------------------------------------------- extracción
def players(mi):
    return {p["player_slot"]: p for p in mi.get("players") or []}


def objectives(mi, objs=None, lanes=None):
    """Una fila por objetivo. `team` es el DUEÑO; lo destruye el rival (destroyed_by)."""
    if objs is None:
        objs, lanes = load_objective_map()
    rows = []
    for o in mi.get("objectives") or []:
        oid = o.get("team_objective_id")
        info = objs.get(oid, {})
        d = o.get("destroyed_time_s") or 0
        rows.append({
            "owner_team": o.get("team"),
            "destroyed_by": 1 - o["team"] if d and o.get("team") in (0, 1) else None,
            "objective_id": oid,
            "type": info.get("tipo", f"#{oid}"),
            "lane": info.get("carril"),
            "label": objective_label(oid, objs, lanes),
            "destroyed_s": d or None,
            "first_damage_s": o.get("first_damage_time_s") or None,
            "creep_damage": o.get("creep_damage"),
            "player_damage": o.get("player_damage"),
        })
    rows.sort(key=lambda r: (r["owner_team"], r["destroyed_s"] or 10 ** 9, r["objective_id"]))
    return rows


def midboss(mi):
    """Muertes del Midboss tal como las da la API: segundo, equipo que lo mata y equipo que lo reclama."""
    out = []
    for i, m in enumerate(mi.get("mid_boss") or []):
        out.append({"n": i + 1, "t": m.get("destroyed_time_s"), "team_killed": m.get("team_killed"), "team_claimed": m.get("team_claimed")})
    return out


def deaths(mi):
    ps = players(mi)
    out = []
    for slot, p in ps.items():
        for d in p.get("death_details") or []:
            dp, kp = d.get("death_pos") or {}, d.get("killer_pos") or {}
            ks = d.get("killer_player_slot")
            killer = ps.get(ks)
            out.append({
                "t": d.get("game_time_s"),
                "victim_slot": slot, "victim_team": p.get("team"), "victim_hero": p.get("hero_id"), "victim_account": p.get("account_id"),
                "killer_slot": ks if killer else None, "killer_team": killer.get("team") if killer else None,
                "killer_hero": killer.get("hero_id") if killer else None,
                "x": dp.get("x"), "y": dp.get("y"), "kx": kp.get("x") if killer else None, "ky": kp.get("y") if killer else None,
            })
    out.sort(key=lambda e: e["t"] or 0)
    return out


def decode_positions(mi, step=1):
    """Posiciones por segundo. x = x_min + x_pos / x_resolution * (x_max - x_min) (igual en y).

    health == 0 = muerto: su posición queda aparcada fuera del mapa y se devuelve como None."""
    mp = mi.get("match_paths") or {}
    xr = mp.get("x_resolution") or 16383
    yr = mp.get("y_resolution") or 16383
    ps = players(mi)
    out = {"interval_s": (mp.get("interval_s") or 1) * step, "players": []}
    for q in mp.get("paths") or []:
        slot = q.get("player_slot")
        p = ps.get(slot, {})
        xs, ys, hp = q.get("x_pos") or [], q.get("y_pos") or [], q.get("health") or []
        x0, x1, y0, y1 = q.get("x_min", 0), q.get("x_max", 0), q.get("y_min", 0), q.get("y_max", 0)
        px, py = [], []
        for i in range(0, min(len(xs), len(ys)), step):
            if i < len(hp) and hp[i] == 0:
                px.append(None)
                py.append(None)
            else:
                px.append(round(x0 + xs[i] / xr * (x1 - x0)))
                py.append(round(y0 + ys[i] / yr * (y1 - y0)))
        out["players"].append({"slot": slot, "team": p.get("team"), "hero_id": p.get("hero_id"), "account_id": p.get("account_id"), "x": px, "y": py})
    out["players"].sort(key=lambda r: (r["team"] if r["team"] is not None else 9, r["slot"]))
    return out


def stat_at(player, field, t):
    """Interpola linealmente un campo de player.stats[] (muestras cada pocos minutos) en el segundo t."""
    st = player.get("stats") or []
    if not st:
        return None
    ts = [s.get("time_stamp_s", 0) for s in st]
    i = bisect.bisect_left(ts, t)
    if i == 0:
        t1, v1 = ts[0], st[0].get(field) or 0
        return v1 * (t / t1) if t1 else v1
    if i >= len(st):
        return st[-1].get(field)
    t0, t1 = ts[i - 1], ts[i]
    v0, v1 = st[i - 1].get(field) or 0, st[i].get(field) or 0
    return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0)


def team_networth_at(mi, team, t):
    return sum(stat_at(p, "net_worth", t) or 0 for p in mi.get("players") or [] if p.get("team") == team)


GOLD_SOURCES = {1: "Kills", 2: "Troopers", 3: "Jungla", 4: "Objetivos", 5: "Tesoro", 6: "Asistencias", 7: "Denies",
                8: "Catch-up de equipo", 9: "Asesinato (habilidad)", 10: "Objeto (10)", 11: "Cultist Sacrifice",
                12: "Rompibles", 13: "Objeto (13)"}


def source_at(player, source, t):
    """Oro acumulado de una fuente (gold_sources[].gold) en el segundo t, interpolado como stat_at."""
    st = player.get("stats") or []
    if not st:
        return None

    def g(s):
        for x in s.get("gold_sources") or []:
            if x.get("source") == source:
                return x.get("gold") or 0
        return 0
    ts = [s.get("time_stamp_s", 0) for s in st]
    i = bisect.bisect_left(ts, t)
    if i == 0:
        v1 = g(st[0])
        return v1 * (t / ts[0]) if ts[0] else v1
    if i >= len(st):
        return g(st[-1])
    t0, t1 = ts[i - 1], ts[i]
    v0, v1 = g(st[i - 1]), g(st[i])
    return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0)


def _cumulative(player, t):
    """Valores acumulados en t: kills de troopers/jungla, net worth y oro por fuente."""
    c = {"troopers_kills": stat_at(player, "creep_kills", t) or 0, "jungla_kills": stat_at(player, "neutral_kills", t) or 0,
         "net_worth": stat_at(player, "net_worth", t) or 0}
    c["troopers_jungla_kills"] = c["troopers_kills"] + c["jungla_kills"]
    for sid in GOLD_SOURCES:
        c[f"fuente_{sid}"] = source_at(player, sid, t) or 0
    return c


def _rates(players, t0, t1):
    """Ritmo por minuto entre t0 y t1 sumando los jugadores dados."""
    mins = (t1 - t0) / 60
    tot = {}
    for p in players:
        a, b = _cumulative(p, t0), _cumulative(p, t1)
        for k in b:
            tot[k] = tot.get(k, 0) + (b[k] - a[k])
    # fase sin duración en esta partida (más allá del final): dato ausente, no 0
    return {k: round(max(v, 0) / mins, 2) if mins > 0 else None for k, v in tot.items()}


def economy(mi):
    """Almas por fuente y ritmos por minuto, por jugador, equipo y fase (0-10, 10-20, 20-fin)."""
    dur = mi.get("duration_s") or 0
    phases = [[0, 600], [600, 1200], [1200, dur]]
    ps = mi.get("players") or []

    def sources(plist):
        out = {}
        for sid in GOLD_SOURCES:
            v = sum(source_at(p, sid, dur) or 0 for p in plist)
            if v:
                out[sid] = round(v)
        return out
    teams = {}
    for tm in (0, 1):
        plist = [p for p in ps if p.get("team") == tm]
        teams[str(tm)] = {"sources": sources(plist), "per_min": _rates(plist, 0, dur),
                          "per_phase": [_rates(plist, a, b) for a, b in phases]}
    players_out = [{"slot": p.get("player_slot"), "team": p.get("team"), "sources": sources([p]), "per_min": _rates([p], 0, dur)}
                   for p in sorted(ps, key=lambda p: (p.get("team"), p.get("player_slot")))]
    return {"phases": phases, "teams": teams, "players": players_out,
            "source_names": dict(GOLD_SOURCES)}


COMEBACK_RATIO = 0.9


def comeback_team_at(mi, t):
    """Equipo en remontada en el segundo t (regla del 10 %: almas < 0,9 × las del rival), o None si ninguno."""
    nw = {tm: team_networth_at(mi, tm, t) for tm in (0, 1)}
    for tm in (0, 1):
        if nw[tm] < COMEBACK_RATIO * nw[1 - tm]:
            return tm
    return None


def comeback_flags(mi, demo):
    """Equipo en remontada (o None) en cada midboss y cada cash-in del KOTH del demo; None si el demo no está listo."""
    if not demo or demo.get("state") != "done":
        return None
    return {"midboss": [comeback_team_at(mi, e["t"]) if e.get("t") is not None else None for e in demo.get("midboss") or []],
            "koth": [comeback_team_at(mi, e["start_t"]) if e.get("start_t") is not None else None for e in demo.get("koth") or []]}


def custom_stat_id(mi, name):
    for c in mi.get("custom_user_stats") or []:
        if c.get("name") == name:
            return c.get("id")
    return None


def final_custom_stat(player, stat_id):
    st = player.get("stats") or []
    if not st or stat_id is None:
        return None
    for c in st[-1].get("custom_user_stats") or []:
        if c.get("id") == stat_id:
            return c.get("value")
    return None


def overview(mi, hero_names=None):
    hero_names = hero_names or {}
    objs, lanes = load_objective_map()
    ps = sorted(mi.get("players") or [], key=lambda p: (p.get("team"), p.get("player_slot")))
    koth_id = custom_stat_id(mi, "Comeback Gold Koth")
    return {
        "match_id": mi.get("match_id"),
        "start_time": mi.get("start_time"),
        "duration_s": mi.get("duration_s"),
        "winning_team": mi.get("winning_team"),
        "game_mode": mi.get("game_mode"),
        "match_mode": mi.get("match_mode"),
        "team_names": TEAM_NAMES,
        "team_names_verified": TEAM_NAMES_VERIFIED,
        "players": [{
            "slot": p.get("player_slot"), "team": p.get("team"), "account_id": p.get("account_id"),
            "hero_id": p.get("hero_id"), "hero": hero_names.get(p.get("hero_id"), f"#{p.get('hero_id')}"),
            "kills": p.get("kills"), "deaths": p.get("deaths"), "assists": p.get("assists"),
            "net_worth": p.get("net_worth"), "last_hits": p.get("last_hits"), "denies": p.get("denies"), "level": p.get("level"),
            "comeback_gold_koth": final_custom_stat(p, koth_id),
            "mvp_rank": p.get("mvp_rank"),
            "player_damage": ((p.get("stats") or [{}])[-1] or {}).get("player_damage"),
            # curva de net worth [[s, oro], ...] para la gráfica de diferencia de oro
            "nw_timeline": [[x.get("time_stamp_s"), x.get("net_worth")] for x in (p.get("stats") or [])
                            if x.get("time_stamp_s") is not None and x.get("net_worth") is not None],
        } for p in ps],
        "objectives": objectives(mi, objs, lanes),
        "midboss": midboss(mi),
        "deaths": deaths(mi),
        "objective_map": {"objetivos": {str(k): v for k, v in objs.items()}, "carriles": {str(k): v for k, v in lanes.items()}},
        "lanes": lanes_payload(),
        "economy": economy(mi),
    }
