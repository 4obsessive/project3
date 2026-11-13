"""Demo: resumen de Midboss, rejuvenators y KOTH a partir de las consultas SQL del demo (parte pura, sin red)."""
import bisect
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import api, db, matches
from .db import now as _db_now

try:
    from compression import zstd
    AVAILABLE = True
except ImportError:  # Python < 3.14
    zstd = None
    AVAILABLE = False
UNAVAILABLE_REASON = "no disponible: requiere Python 3.14+"

TICK_RATE = 64
# El demo numera los equipos 2 y 3; la API de partidas usa 0 y 1.
TEAM_TO_API = {2: 0, 3: 1}
# 2: KOTH sin restar dos veces las pausas; Midboss sin daño capturado -> damage None.
SUMMARY_VERSION = 2
# Ventana tras el último daño al Midboss en la que un rejuvenator cuenta como suyo.
KILL_WINDOW_S = 30
# Rejuvenators del mismo equipo separados menos de esto pertenecen al mismo Midboss.
CLUSTER_GAP_S = 60
# koth_give_up vale ~3.4e38 mientras el cash-in sigue abierto.
GIVE_UP_INFINITE = 1e30

QUERIES = {
    "rejuv": "SELECT tick, killing_team, user_team FROM RejuvStatusEvent WHERE event_type = 4 ORDER BY tick",
    "rules": "SELECT min(tick) AS tick, \"m_pGameRules__m_nKothScoringTeam\" AS koth_team, \"m_pGameRules__m_timeKothScoring\" AS koth_scoring, \"m_pGameRules__m_timeKothCashInStarted\" AS koth_start, \"m_pGameRules__m_timeKothGiveUp\" AS koth_give_up, \"m_pGameRules__m_nTotalPausedTicks\" AS paused_ticks, \"m_pGameRules__m_flGameStartTime\" AS game_start FROM CCitadelGameRulesProxy GROUP BY 2,3,4,5,6,7 ORDER BY 1",
    "midboss": "SELECT d.entindex_victim AS victim, p.team AS team, sum(d.damage) AS dmg, min(d.tick) AS t0, max(d.tick) AS t1 FROM DamageEvent d JOIN (SELECT DISTINCT entity_index, \"m_iTeamNum\" AS team FROM CCitadelPlayerPawn WHERE \"m_iTeamNum\" IS NOT NULL) p ON d.entindex_attacker = p.entity_index WHERE d.victim_class = 8 GROUP BY 1,2 ORDER BY 4",
}


def _fila_vigente(tick, rules):
    """Última fila de `rules` con tick <= el dado (o None). `rules` viene ordenado por tick."""
    ticks = [r["tick"] for r in rules]
    i = bisect.bisect_right(ticks, tick) - 1
    return rules[i] if i >= 0 else None


def game_seconds_from_tick(tick, rules):
    """Segundos de partida de un tick: (tick - ticks pausados vigentes) / 64."""
    fila = _fila_vigente(tick, rules)
    pausados = (fila or {}).get("paused_ticks") or 0
    return (tick - pausados) / TICK_RATE


def game_seconds_from_curtime(curtime, tick, rules):
    """Segundos de partida de un valor curtime (columnas koth_*) observado en `tick`.

    El curtime ya excluye el tiempo en pausa, así que solo se resta el inicio de la partida."""
    fila = _fila_vigente(tick, rules)
    if fila is None:
        return float(curtime)
    return curtime - fila["game_start"]


def _api(team):
    return TEAM_TO_API.get(team)


def _cumulos_rejuv(rejuv):
    """Agrupa filas de rejuvenator por killing_team, con menos de 60 s entre filas consecutivas."""
    abiertos = {}
    cumulos = []
    for r in sorted(rejuv, key=lambda x: x["tick"]):
        team = r["killing_team"]
        c = abiertos.get(team)
        if c is None or r["tick"] - c["rows"][-1]["tick"] > CLUSTER_GAP_S * TICK_RATE:
            c = {"team": team, "rows": []}
            abiertos[team] = c
            cumulos.append(c)
        c["rows"].append(r)
    return cumulos


def _contar_rejuv(rows):
    """Rejuvenators por equipo del usuario (numeración API, claves string)."""
    cuenta = {"0": 0, "1": 0}
    for r in rows:
        t = _api(r["user_team"])
        if t is not None:
            cuenta[str(t)] += 1
    return cuenta


def _midboss(results, rules):
    entidades = {}
    for r in results.get("midboss") or []:
        e = entidades.setdefault(r["victim"], {"filas": [], "t1": 0})
        e["filas"].append(r)
        e["t1"] = max(e["t1"], r["t1"])
    lista = []
    for e in entidades.values():
        dmg = {"0": 0, "1": 0}
        con_dano = [f for f in e["filas"] if f["dmg"] > 0 and _api(f["team"]) is not None]
        for f in con_dano:
            dmg[str(_api(f["team"]))] += f["dmg"]
        # Inicia el equipo que más daño hizo; empate (o 0 en ambos) -> None, sin inventar.
        inicia = None if dmg["0"] == dmg["1"] else (0 if dmg["0"] > dmg["1"] else 1)
        lista.append({"t_tick": e["t1"], "damage": dmg,
                      "initiator": inicia,
                      "killer": None, "rejuv_rows": []})
    lista.sort(key=lambda x: x["t_tick"])

    sueltos = []
    for c in _cumulos_rejuv(results.get("rejuv") or []):
        primero = c["rows"][0]["tick"]
        # Entidad más reciente cuyo último daño cae en los 30 s previos al cúmulo.
        destino = None
        for e in lista:
            if 0 <= primero - e["t_tick"] <= KILL_WINDOW_S * TICK_RATE:
                destino = e
        if destino is None:
            # Sin daño capturado: el daño es un dato ausente (None), no 0.
            sueltos.append({"t_tick": primero, "damage": None, "initiator": None,
                            "killer": _api(c["team"]), "rejuv_rows": c["rows"]})
        else:
            destino["rejuv_rows"].extend(c["rows"])
            destino["killer"] = _api(c["team"])

    # Sin daño en ningún equipo y sin rejuvenators: no es un Midboss real.
    entradas = [e for e in lista if sum(e["damage"].values()) > 0 or e["rejuv_rows"]] + sueltos  # lista: damage siempre dict
    entradas.sort(key=lambda x: x["t_tick"])

    salida = []
    for n, e in enumerate(entradas, 1):
        ini, kil = e["initiator"], e["killer"]
        salida.append({
            "n": n,
            "t": round(game_seconds_from_tick(e["t_tick"], rules)),
            "damage": e["damage"],
            "initiator": ini,
            "killer": kil,
            "stolen": (kil != ini) if ini is not None and kil is not None else None,
            "rejuv": _contar_rejuv(e["rejuv_rows"]),
        })
    return salida


def _koth(rules):
    # Un cash-in = cada koth_start > 0 distinto con koth_give_up finito; se guarda la primera fila en que aparece.
    inicios = []
    vistos = set()
    for r in rules:
        s = r["koth_start"]
        if s > 0 and r["koth_give_up"] < GIVE_UP_INFINITE and s not in vistos:
            vistos.add(s)
            inicios.append(r)
    salida = []
    for n, ini in enumerate(inicios, 1):
        limite = inicios[n]["tick"] if n < len(inicios) else None
        hecho = None
        for r in rules:
            if r["tick"] < ini["tick"]:
                continue
            if limite is not None and r["tick"] >= limite:
                break
            if r["koth_team"] in TEAM_TO_API and r["koth_scoring"] >= ini["koth_start"]:
                hecho = r
                break
        salida.append({
            "n": n,
            "start_t": round(game_seconds_from_curtime(ini["koth_start"], ini["tick"], rules)),
            "completed_by": _api(hecho["koth_team"]) if hecho else None,
            "completed_t": round(game_seconds_from_curtime(hecho["koth_scoring"], hecho["tick"], rules))
            if hecho else None,
        })
    return salida


def summarize(results):
    """Resume los resultados de las consultas del demo en un dict serializable a JSON."""
    rules = sorted(results.get("rules") or [], key=lambda r: r["tick"])
    return {"version": SUMMARY_VERSION, "midboss": _midboss(results, rules), "koth": _koth(rules)}


# ------------------------------------------------------------------ red
QUERY_HOST = "api.deadlock-api.com"
RESULT_HOST = "demo-extracts.deadlock-api.com"
QUERY_URL = f"https://{QUERY_HOST}/v1/matches/demo/query"
MAX_RESULT = 20 * 1024 * 1024
MAX_DECOMPRESSED = 100 * 1024 * 1024
NODEMO_MARKERS = ("No demo available", "Failed to fetch match salts")
KV_POSTS = "demo_post_times"
KV_PAUSE = "demo_pause_until"
POLL_EVERY_S = 3
POLL_MAX_S = 120
BUDGET_WINDOW_S = 3600
RATE_LIMIT_WAIT_S = 61
MAX_ATTEMPTS = 5


class DemoError(Exception):
    """Fallo reintentable."""


class DemoFatal(DemoError):
    """Fallo que no se reintenta (respuesta que no debemos aceptar)."""


class NoDemo(Exception):
    """La API no tiene el demo de la partida."""


class RateLimited(Exception):
    """HTTP 429."""


class _HostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlsplit(newurl)
        if u.scheme != "https" or u.hostname not in (QUERY_HOST, RESULT_HOST):
            fp.close()
            raise urllib.error.HTTPError(newurl, code, f"Redirección a host no permitido: {u.hostname}", headers, None)
        nueva = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nueva is not None and u.hostname != QUERY_HOST:
            nueva.remove_header("X-api-key")  # la clave solo viaja a la API de consultas
        return nueva


class DemoClient:
    """Cliente de las consultas SQL del demo. `opener` debe tener `.open(req, timeout=)`."""

    def __init__(self, opener=None, now=time.time, sleep=time.sleep, api_key=""):
        self.opener = opener or urllib.request.build_opener(_HostRedirect)
        self.now = now
        self.sleep = sleep
        self.api_key = api_key or ""
        self.post_times = []  # instantes de los POST (ventana deslizante del presupuesto)

    def posts_last_hour(self):
        corte = self.now() - BUDGET_WINDOW_S
        self.post_times[:] = [t for t in self.post_times if t > corte]
        return len(self.post_times)

    def _request(self, url, body=None):
        """GET, o POST si hay `body`. Solo un 404 del POST con el mensaje conocido significa «sin demo»."""
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https" or u.hostname not in (QUERY_HOST, RESULT_HOST):
            raise DemoFatal(f"host no permitido: {u.hostname}")
        headers = {"User-Agent": api.USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key and u.hostname == QUERY_HOST:
            headers["X-API-KEY"] = self.api_key  # misma cabecera que scouting.api.Client
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
        if body is not None:
            self.post_times.append(self.now())
        try:
            with self.opener.open(req, timeout=60) as r:
                raw = r.read(MAX_RESULT + 1)
        except urllib.error.HTTPError as e:
            try:
                msg = e.read(300).decode("utf-8", "replace")
            except Exception:
                msg = ""
            finally:
                e.close()
            if e.code == 429:
                raise RateLimited()
            if e.code == 404 and body is not None and any(m in msg for m in NODEMO_MARKERS):
                raise NoDemo()
            raise DemoError(f"HTTP {e.code}: {msg}")
        if len(raw) > MAX_RESULT:
            raise DemoFatal("respuesta demasiado grande")
        return raw

    def run_queries(self, match_id):
        """Lanza las 3 consultas del demo y devuelve `results` (formato del fixture)."""
        results = {"match_id": int(match_id)}
        for nombre, sql in QUERIES.items():
            job = json.loads(self._request(QUERY_URL, {"match_id": int(match_id), "query": sql, "format": "ndjson"}))
            job_id = job.get("job_id")
            if not job_id:
                raise DemoError("la API no devolvió job_id")
            results[nombre] = self._esperar(job_id)
        return results

    def _esperar(self, job_id):
        url = f"{QUERY_URL}/{urllib.parse.quote(str(job_id), safe='')}"
        for _ in range(POLL_MAX_S // POLL_EVERY_S):
            st = json.loads(self._request(url))
            estado = st.get("status")
            if estado == "done":
                ru = st.get("result_url") or ""
                u = urllib.parse.urlsplit(ru)
                if u.scheme != "https" or u.hostname != RESULT_HOST:
                    raise DemoFatal(f"result_url de un host no permitido: {u.hostname}")
                return self._parse(self._request(ru))
            if estado == "failed":
                raise DemoError(f"consulta fallida: {st.get('error')}")
            self.sleep(POLL_EVERY_S)
        raise DemoError("tiempo de espera agotado")

    @staticmethod
    def _parse(raw):
        if zstd is None:
            raise DemoFatal(UNAVAILABLE_REASON)
        try:
            dec = zstd.ZstdDecompressor()
            crudo = dec.decompress(raw, max_length=MAX_DECOMPRESSED + 1)
            if len(crudo) > MAX_DECOMPRESSED:
                raise DemoError("resultado descomprimido demasiado grande")
            if not dec.eof:
                raise DemoError("resultado truncado")
            texto = crudo.decode("utf-8")
            return [json.loads(l) for l in texto.splitlines() if l.strip()]
        except (ValueError, zstd.ZstdError) as e:
            raise DemoError(f"resultado ilegible: {e}")


# ------------------------------------------------------------------ cola
def _json(obj):
    return json.dumps(obj, separators=(",", ":"))


def enqueue(con, match_id):
    """Encola una partida como `pending` si aún no tiene fila (no toca done/nodemo)."""
    with con:
        con.execute("INSERT OR IGNORE INTO demo_jobs(match_id, state, updated_at) VALUES(?, 'pending', ?)",
                    (int(match_id), _db_now()))


def summary(con, match_id):
    """Estado del demo de una partida: resumen si está listo; si no, estado y motivo."""
    if not AVAILABLE:
        return {"state": "unavailable", "reason": UNAVAILABLE_REASON}
    r = con.execute("SELECT state, summary, raw, error FROM demo_jobs WHERE match_id=?", (int(match_id),)).fetchone()
    if r is None:
        return {"state": "pending", "reason": "aún sin consultar"}
    if r["state"] == "done" and r["summary"]:
        s = json.loads(r["summary"])
        if s.get("version") != SUMMARY_VERSION and r["raw"]:
            # Resumen de una versión anterior: se rehace desde las filas crudas guardadas y se persiste.
            s = summarize(json.loads(r["raw"]))
            with con:
                con.execute("UPDATE demo_jobs SET summary=? WHERE match_id=?", (_json(s), int(match_id)))
        return {"state": "done", **s}
    if r["state"] == "nodemo":
        return {"state": "nodemo", "reason": "la API no tiene el demo de esta partida"}
    if r["state"] == "error":
        return {"state": "error", "reason": r["error"] or "error al consultar el demo"}
    return {"state": "pending", "reason": "en cola"}


def counts(con):
    """Recuento de partidas por estado."""
    out = {"pending": 0, "done": 0, "nodemo": 0, "error": 0}
    for r in con.execute("SELECT state, COUNT(*) n FROM demo_jobs GROUP BY state"):
        out[r["state"]] = r["n"]
    out["available"] = AVAILABLE
    return out


class Worker:
    """Procesa la cola de a una partida, respetando un presupuesto de POST por hora."""

    def __init__(self, con_factory, client, budget_per_hour=150):
        self.con_factory = con_factory
        self.client = client
        self.budget = budget_per_hour
        self._pausa_hasta = 0
        self._cargar()
        self._stop = threading.Event()
        self._thread = None

    def _cargar(self):
        """Recupera de la BD los POST de la última hora y la pausa por 429 (sobreviven a reinicios)."""
        try:
            con = self.con_factory()
            ts = json.loads(db.kv_get(con, KV_POSTS) or "[]")
            self.client.post_times.extend(float(t) for t in ts)
            self._pausa_hasta = float(db.kv_get(con, KV_PAUSE) or 0)
        except Exception as e:
            print(f"[demo] no se pudo cargar el presupuesto: {e}")

    def _guardar(self, con):
        self.client.posts_last_hour()
        with con:
            db.kv_set(con, KV_POSTS, json.dumps(self.client.post_times))
            db.kv_set(con, KV_PAUSE, self._pausa_hasta)

    def step(self):
        """Procesa una partida. False si no hay nada pendiente o no hay presupuesto."""
        t = self.client.now()
        if t < self._pausa_hasta or self.budget - self.client.posts_last_hour() < len(QUERIES):
            return False
        con = self.con_factory()
        fila = con.execute("SELECT match_id, attempts FROM demo_jobs WHERE state='pending' AND next_try<=? "
                           "ORDER BY match_id DESC LIMIT 1", (int(t),)).fetchone()
        if fila is None:
            return False
        mid, intentos = fila["match_id"], fila["attempts"]
        try:
            return self._procesar(con, t, mid, intentos)
        finally:
            self._guardar(con)

    def _procesar(self, con, t, mid, intentos):
        try:
            res = self.client.run_queries(mid)
            try:
                resumen = summarize(res)
            except Exception as e:  # determinista: reintentar solo gastaría presupuesto
                raise DemoFatal(f"no se pudo resumir el demo: {e!r}")
            self._marcar(con, mid, "done", summary=_json(resumen), raw=_json(res), error=None)
        except NoDemo:
            self._marcar(con, mid, "nodemo", error=None)
        except RateLimited:
            self._pausa_hasta = t + RATE_LIMIT_WAIT_S
            self._marcar(con, mid, "pending", next_try=int(t + RATE_LIMIT_WAIT_S))
        except Exception as e:
            intentos += 1
            fatal = isinstance(e, DemoFatal) or intentos >= MAX_ATTEMPTS
            print(f"[demo] partida {mid}: {e}")
            self._marcar(con, mid, "error" if fatal else "pending", error=str(e)[:300], attempts=intentos,
                         next_try=int(t + 600 * intentos))
        return True

    @staticmethod
    def _marcar(con, mid, estado, **campos):
        campos.update(state=estado, updated_at=_db_now())
        cols = ", ".join(f"{k}=?" for k in campos)
        with con:
            con.execute(f"UPDATE demo_jobs SET {cols} WHERE match_id=?", (*campos.values(), mid))

    def _loop(self):
        while not self._stop.is_set():
            try:
                trabajo = self.step()
            except Exception as e:
                print(f"[demo] error del trabajador: {e}")
                trabajo = False
            if not trabajo:
                self._stop.wait(5)

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="demo")
            self._thread.start()

    def stop(self):
        self._stop.set()


def enqueue_hook(con, match_id):
    enqueue(con, match_id)


def install(con, api_key="", start_worker=True):
    """Registra el gancho de guardado, encola las partidas sin fila y arranca el trabajador."""
    if enqueue_hook not in matches.ON_STORE:
        matches.ON_STORE.append(enqueue_hook)
    with con:
        con.execute("INSERT OR IGNORE INTO demo_jobs(match_id, state, updated_at) "
                    "SELECT match_id, 'pending', ? FROM matches", (_db_now(),))
        # Filas `done` de antes de guardar las filas crudas: se vuelven a consultar (una vez) con el resumen corregido.
        con.execute("UPDATE demo_jobs SET state='pending', attempts=0, next_try=0, updated_at=? "
                    "WHERE state='done' AND raw IS NULL", (_db_now(),))
    if not (AVAILABLE and start_worker):
        return None
    w = Worker(db.get, DemoClient(api_key=api_key))
    w.start()
    return w
