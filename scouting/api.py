"""Cliente de https://api.deadlock-api.com con lotes, caché de assets y backoff ante 429/5xx."""
import gzip
import json
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from . import config

BASE = "https://api.deadlock-api.com"
USER_AGENT = "deadlock-scouting-local/1.0"
CACHE_DIR = os.path.join(config.DATA_DIR, "cache")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


ALLOWED_HOST = urllib.parse.urlsplit(BASE).hostname
MAX_RESPONSE = 200 * 1024 * 1024


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlsplit(newurl)
        if u.scheme != "https" or u.hostname != ALLOWED_HOST:
            raise urllib.error.HTTPError(newurl, code, f"Redirección a host no permitido: {u.hostname}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SameHostRedirect)


def _read_capped(r, limit=MAX_RESPONSE):
    body = r.read(limit + 1)
    if len(body) > limit:
        raise ApiError(0, "respuesta demasiado grande")
    return body


class Client:
    def __init__(self, api_key="", min_interval=0.05, max_retries=6):
        self.api_key = api_key or ""
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._lock = threading.Lock()
        self._last = 0.0

    # ------------------------------------------------------------------ base
    def _throttle(self):
        with self._lock:
            wait = self._last + self.min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()

    def get_raw(self, path, params=None, timeout=120, min_429_wait=0):
        url = BASE + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            url += "?" + urllib.parse.urlencode(clean, safe=",")
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            self._throttle()
            req = urllib.request.Request(url, headers=headers)
            try:
                with _opener.open(req, timeout=timeout) as r:
                    body = _read_capped(r)
                    if r.headers.get("Content-Encoding") == "gzip":
                        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
                        body = d.decompress(body, MAX_RESPONSE + 1)
                        if len(body) > MAX_RESPONSE or d.unconsumed_tail:
                            raise ApiError(0, "respuesta demasiado grande")
                    return body
            except urllib.error.HTTPError as e:
                msg = e.read()[:300].decode("utf-8", "replace")
                if e.code == 429 or e.code >= 500:
                    if attempt == self.max_retries:
                        raise ApiError(e.code, msg)
                    ra = e.headers.get("Retry-After")
                    try:
                        wait = float(ra) if ra else delay
                    except ValueError:
                        wait = delay
                    if e.code == 429:
                        # la API cuenta también las peticiones rechazadas: en endpoints con cuota
                        # por cuentas hay que dejar pasar la ventana entera
                        wait = max(wait, min_429_wait)
                    wait = min(wait, 120) + random.random()
                    print(f"[api] {e.code} en {path}; reintento en {wait:.0f} s")
                    time.sleep(wait)
                    delay = min(delay * 2, 120)
                    continue
                raise ApiError(e.code, msg)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt == self.max_retries:
                    raise ApiError(0, str(e))
                time.sleep(delay)
                delay = min(delay * 2, 120)
        raise ApiError(0, "sin respuesta")

    def get_json(self, path, params=None, timeout=120, min_429_wait=0):
        return json.loads(self.get_raw(path, params, timeout, min_429_wait))

    def cached_json(self, name, path, params=None, ttl_s=7 * 86400):
        """Caché en disco para assets que cambian poco (héroes, mapa, temporadas)."""
        os.makedirs(CACHE_DIR, exist_ok=True)
        fp = os.path.join(CACHE_DIR, name + ".json")
        if os.path.exists(fp) and time.time() - os.path.getmtime(fp) < ttl_s:
            with open(fp, encoding="utf-8") as f:
                return json.load(f)
        try:
            data = self.get_json(path, params)
        except ApiError:
            if os.path.exists(fp):  # mejor datos viejos que nada
                with open(fp, encoding="utf-8") as f:
                    return json.load(f)
            raise
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    # ------------------------------------------------------------ endpoints
    def leaderboard(self, region, leaderboard_id=None):
        return self.get_json(f"/v1/leaderboard/{region}", {"leaderboard_id": leaderboard_id})["entries"]

    def ranked_seasons(self):
        return self.cached_json("ranked_seasons", "/v1/assets/ranked-seasons", ttl_s=86400)

    def heroes(self):
        return self.cached_json("heroes", "/v1/assets/heroes")

    def map_asset(self):
        return self.cached_json("map", "/v1/assets/map")

    def hero_stats(self, account_ids, min_unix_timestamp=None):
        ids = ",".join(str(int(a)) for a in account_ids)
        return self.get_json("/v1/players/hero-stats", {"account_ids": ids, "min_unix_timestamp": min_unix_timestamp})

    def ranks(self, account_ids):
        """Límite documentado: 10 000 cuentas/min y 100 000/h por IP (cada cuenta del lote cuenta).
        Se reparte a 8 000/min para no provocar 429 (y si llega uno, se espera la ventana entera)."""
        account_ids = list(account_ids)
        self._account_budget(len(account_ids))
        ids = ",".join(str(int(a)) for a in account_ids)
        return self.get_json("/v1/players/rank", {"account_ids": ids}, min_429_wait=61)

    def _account_budget(self, n, per_min=8000):
        with self._lock:
            now = time.time()
            self._rank_log = [(t, k) for t, k in getattr(self, "_rank_log", []) if now - t < 60]
            used = sum(k for _, k in self._rank_log)
            wait = 0.0
            if used + n > per_min and self._rank_log:
                # esperar a que salgan de la ventana suficientes cuentas
                acc = used + n - per_min
                for t, k in self._rank_log:
                    acc -= k
                    if acc <= 0:
                        wait = 60 - (now - t) + 0.5
                        break
            self._rank_log.append((now + wait, n))
        if wait > 0:
            time.sleep(wait)

    def steam(self, account_ids):
        ids = ",".join(str(int(a)) for a in account_ids)
        return self.get_json("/v1/players/steam", {"account_ids": ids})

    def mate_stats(self, account_id, min_unix_timestamp=None, same_party=True):
        return self.get_json(
            f"/v1/players/{int(account_id)}/mate-stats",
            {"same_party": "true" if same_party else "false", "min_unix_timestamp": min_unix_timestamp},
        )

    def match_history(self, account_id):
        return self.get_json(f"/v1/players/{int(account_id)}/match-history")

    def match_metadata_raw(self, match_id):
        return self.get_raw(f"/v1/matches/{int(match_id)}/metadata", timeout=180)


def current_leaderboard_id(seasons, now=None):
    """Devuelve el leaderboard_id del intervalo de temporada activo (o el último)."""
    now = now or time.time()
    best = None
    for s in seasons or []:
        for iv in s.get("intervals", []):
            lid = iv.get("leaderboard_id")
            if lid is None:
                continue
            if iv.get("start_timestamp", 0) <= now < iv.get("end_timestamp", 1 << 62):
                return lid, s.get("name")
            if best is None or iv.get("start_timestamp", 0) > best[2]:
                best = (lid, s.get("name"), iv.get("start_timestamp", 0))
    return (best[0], best[1]) if best else (None, None)


def season_names(seasons):
    out = {}
    for s in seasons or []:
        for iv in s.get("intervals", []):
            if iv.get("leaderboard_id") is not None:
                out[iv["leaderboard_id"]] = s.get("name")
    return out
