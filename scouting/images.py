"""Proxy-caché de imágenes (wiki de Deadlock y assets de la API).

El navegador solo puede cargar imágenes de la propia app (CSP img-src 'self'), así que el servidor las
descarga de los dos orígenes permitidos, las guarda en data/cache/img/<origen>/ y las sirve desde ahí."""
import mimetypes
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from . import config

SOURCES = {"wiki": "https://cdn.deadlock.wiki/",
           "api": "https://assets-bucket.deadlock-api.com/assets-api-res/images/"}
MAX_SEGMENTS = {"wiki": 1, "api": 3}
CACHE_DIR = os.path.join(config.DATA_DIR, "cache", "img")
MAX_BYTES = 5 * 1024 * 1024
FAIL_TTL = 600
TIMEOUT = 15
USER_AGENT = "deadlock-scouting-local/1.0"

_SEGMENT = re.compile(r"[A-Za-z0-9_\-.&%()]+\Z")
_EXT = re.compile(r"\.(png|jpe?g|webp)\Z", re.I)
_FAILED = {}
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def safe_name(origin, name):
    """Devuelve el nombre (ya decodificado) si es válido para ese origen; si no, None."""
    if origin not in SOURCES or not isinstance(name, str) or not name:
        return None
    parts = name.split("/")
    if len(parts) > MAX_SEGMENTS[origin]:
        return None
    for p in parts:
        if not _SEGMENT.match(p) or not p.strip("."):
            return None
    if not _EXT.search(parts[-1]):
        return None
    return name


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_urlopen = urllib.request.build_opener(_NoRedirect)


def _default_opener(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with _urlopen.open(req, timeout=TIMEOUT) as r:
            return r.status, dict(r.headers), r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:  # incluye redirecciones no seguidas
        return e.code, {}, b""


def _paths(origin, name):
    fp = os.path.join(CACHE_DIR, origin, *name.split("/"))
    return fp, fp + ".type"


def _ctype_of(fp):
    try:
        with open(fp + ".type", encoding="ascii") as f:
            t = f.read().strip()
        if t.startswith("image/"):
            return t
    except OSError:
        pass
    return mimetypes.guess_type(fp)[0] or "application/octet-stream"


def _write(fp, data):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    tmp = f"{fp}.{threading.get_ident()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, fp)


def _read_cached(fp):
    """(bytes, content-type) del archivo en caché, o None si no existe o no se puede leer."""
    try:
        with open(fp, "rb") as f:
            return f.read(), _ctype_of(fp)
    except OSError:
        return None


def get(origin, name, opener=None):
    """(bytes, content-type) de la imagen, descargándola si hace falta; None si no está disponible."""
    name = safe_name(origin, name)
    if name is None:
        return None
    fp, tp = _paths(origin, name)
    if os.path.isfile(fp):
        return _read_cached(fp)
    key = (origin, name)
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.Lock())
    try:
        with lock:
            if os.path.isfile(fp):  # otro hilo la acaba de bajar
                return _read_cached(fp)
            ts = _FAILED.get(key)
            if ts is not None and time.time() - ts < FAIL_TTL:
                return None
            url = SOURCES[origin] + urllib.parse.quote(name, safe="/")
            try:
                status, headers, body = (opener or _default_opener)(url)
            except Exception:
                status, headers, body = 0, {}, b""
            ctype = ""
            for k, v in (headers or {}).items():
                if k.lower() == "content-type":
                    ctype = str(v).split(";")[0].strip().lower()
            if (status != 200 or not ctype.startswith("image/") or ctype == "image/svg+xml"
                    or not body or len(body) > MAX_BYTES):
                now = time.time()
                for k in [k for k, t in _FAILED.items() if now - t >= FAIL_TTL]:
                    _FAILED.pop(k, None)
                _FAILED[key] = now
                return None
            try:
                _write(fp, body)
                _write(tp, ctype.encode("ascii", "ignore"))
            except OSError:
                pass  # sin caché en disco, pero se sirve igual
            return body, ctype
    finally:
        with _LOCKS_GUARD:
            _LOCKS.pop(key, None)
