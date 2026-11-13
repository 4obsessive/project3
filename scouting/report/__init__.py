"""Informe de equipo como registro de métricas.

Cada métrica es una función registrada con @metric que recibe un ReportCtx y devuelve una lista de
bloques (o un dict {"blocks": [...], "findings": [...]}). La web pinta los bloques sin conocer la
métrica. Para añadir una métrica basta con crear un archivo en scouting/report/metricas/.

Tipos de bloque:
  text        {text, tone: confirmed|warning|info}
  table       {title, columns:[{key,label,fmt}], rows:[{...}], n}
  bars        {title, labels:[...], series:[{name, values, side}], unit, n}
  histogram   {title, series:[{name, values(s), side}], bin_s, n}
  timeline    {title, rows:[{label, events:[{t, label, side, kind}]}], n}
  map         {title, layers:[{kind: points|crosses|cells, name, side, points:[[x,y]], cells:[[col,row,v]]}], grid, normalized, n}
  unavailable {title, reason}
Cada bloque con estadísticas lleva `n` (número de partidas en las que se basa)."""
import importlib
import pkgutil
import statistics
import traceback

from .. import matches as M

METRICS = []
SMALL_SAMPLE = 10
GRID = 8  # cuadrícula de zonas sobre el minimapa (A–H × 1–8)


def metric(id, title, order=100):
    def deco(fn):
        METRICS.append({"id": id, "title": title, "order": order, "fn": fn})
        METRICS.sort(key=lambda m: m["order"])
        return fn
    return deco


def _load_all():
    from . import metricas
    for mod in pkgutil.iter_modules(metricas.__path__):
        importlib.import_module(f"{metricas.__name__}.{mod.name}")


# ------------------------------------------------------------------ contexto
class MatchCtx:
    def __init__(self, data, our, side_source, roster_counts):
        self.data = data
        self.mi = data["match_info"]
        self.id = self.mi["match_id"]
        self.our = our
        self.their = 1 - our
        self.side_source = side_source
        self.roster_counts = roster_counts
        self.duration = self.mi.get("duration_s") or 0
        self.won = self.mi.get("winning_team") == our
        self._deaths = None
        self._objs = None

    @property
    def deaths(self):
        if self._deaths is None:
            self._deaths = M.deaths(self.mi)
        return self._deaths

    @property
    def objectives(self):
        if self._objs is None:
            self._objs = M.objectives(self.mi)
        return self._objs

    def rel(self, team):
        if team is None:
            return None
        return "us" if team == self.our else "them"

    def norm(self, x, y, normalize):
        """Gira 180° las partidas del equipo 1 para que la base propia quede siempre abajo."""
        if normalize and self.our == 1:
            return -x, -y
        return x, y


class ReportCtx:
    def __init__(self, team, matches, params, skipped):
        self.team = team
        self.matches = matches
        self.params = params
        self.skipped = skipped
        self.n = len(matches)
        self.findings = []

    def finding(self, kind, text, support=None, total=None):
        """kind: strength | weakness | pattern | improve | opportunity"""
        self.findings.append({"kind": kind, "text": text, "support": support, "total": total})

    def sample_warning(self, n=None, what="partidas"):
        n = self.n if n is None else n
        if n < SMALL_SAMPLE:
            return {"type": "text", "tone": "warning", "text": f"Muestra pequeña: {n} {what} (< {SMALL_SAMPLE}). Tómalo como indicio, no como patrón."}
        return None


# ------------------------------------------------------------ utilidades
def stats(values):
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {"n": len(v), "mean": sum(v) / len(v), "median": statistics.median(v), "min": min(v), "max": max(v)}


def cell_of(x, y, cal):
    u = (x - cal["x_min"]) / (cal["x_max"] - cal["x_min"])
    v = (y - cal["y_min"]) / (cal["y_max"] - cal["y_min"])
    if cal.get("invert_x"):
        u = 1 - u
    if cal.get("invert_y", True):
        v = 1 - v
    if not (0 <= u < 1 and 0 <= v < 1):
        return None
    return int(u * GRID), int(v * GRID)


def cell_name(c):
    return f"{'ABCDEFGH'[c[0]]}{c[1] + 1}"


def detect_side(mi, roster):
    counts = {0: 0, 1: 0}
    for p in mi.get("players") or []:
        if p.get("account_id") in roster and p.get("team") in counts:
            counts[p["team"]] += 1
    if counts[0] == counts[1]:
        return None, counts
    return (0 if counts[0] > counts[1] else 1), counts


# ------------------------------------------------------------------- run
def run(team, match_datas, roster, side_overrides=None, params=None):
    _load_all()
    params = dict({"midboss_window_s": 90, "normalize": True}, **(params or {}))
    side_overrides = {int(k): int(v) for k, v in (side_overrides or {}).items() if v in (0, 1, "0", "1")}
    ctxs, skipped, sides = [], [], []
    for d in match_datas:
        mi = d["match_info"]
        auto, counts = detect_side(mi, roster)
        mid = mi["match_id"]
        if mid in side_overrides:
            our, src = side_overrides[mid], "manual"
        else:
            our, src = auto, "auto"
        sides.append({"match_id": mid, "auto": auto, "side": our, "source": src, "roster_counts": counts})
        if our is None:
            skipped.append({"match_id": mid, "reason": "No se pudo detectar el lado (ningún jugador de la plantilla o empate). Elige el lado a mano."})
            continue
        ctxs.append(MatchCtx(d, our, src, counts))
    ctx = ReportCtx(team, ctxs, params, skipped)
    sections = []
    conclusions = None
    for m in METRICS:
        if m["id"] == "conclusiones":
            conclusions = m
            continue
        sections.append(_run_one(m, ctx))
    if conclusions:
        sections.append(_run_one(conclusions, ctx))
    return {"team": team, "n": ctx.n, "params": params, "sides": sides, "skipped": skipped, "our_heroes": _our_heroes(ctxs),
            "lanes": M.lanes_payload(), "team_names": M.TEAM_NAMES, "team_names_verified": M.TEAM_NAMES_VERIFIED, "sections": sections}


def _our_heroes(ctxs, limit=12):
    """Héroes del lado propio: partidas analizadas en que aparece cada uno (máx. `limit`, más usados primero)."""
    counts = {}
    for m in ctxs:
        seen = {p.get("hero_id") for p in m.mi.get("players") or [] if p.get("team") == m.our and p.get("hero_id") is not None}
        for h in seen:
            counts[h] = counts.get(h, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [{"hero_id": h, "matches": n} for h, n in ranked]


def _run_one(m, ctx):
    try:
        if ctx.n == 0 and m["id"] != "conclusiones":
            return {"id": m["id"], "title": m["title"], "blocks": [{"type": "unavailable", "title": m["title"], "reason": "No hay partidas con lado detectado."}]}
        out = m["fn"](ctx)
        if isinstance(out, dict):
            blocks = out.get("blocks", [])
        else:
            blocks = out or []
        return {"id": m["id"], "title": m["title"], "blocks": [b for b in blocks if b]}
    except Exception as e:  # si una métrica falla, solo falla su sección
        traceback.print_exc()
        return {"id": m["id"], "title": m["title"], "error": f"{type(e).__name__}: {e}", "blocks": []}


def list_metrics():
    _load_all()
    return [{"id": m["id"], "title": m["title"], "order": m["order"]} for m in METRICS]
