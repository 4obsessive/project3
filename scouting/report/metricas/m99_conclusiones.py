"""Conclusiones generales a partir de los hallazgos que registran las demás métricas."""
from .. import SMALL_SAMPLE, metric

GROUPS = [
    ("strength", "Strengths"),
    ("weakness", "Weaknesses"),
    ("pattern", "Repeated patterns"),
    ("improve", "What to improve"),
    ("opportunity", "Tactical opportunities"),
]


@metric("conclusiones", "Overall conclusions", order=999)
def conclusiones(ctx):
    blocks = []
    if ctx.n == 0:
        return [{"type": "unavailable", "title": "Conclusions", "reason": "No matches with a detected side."}]
    if ctx.n < SMALL_SAMPLE:
        blocks.append({"type": "text", "tone": "warning",
                       "text": f"With {ctx.n} matches the conclusions are only indicative. To speak of patterns, aim for {SMALL_SAMPLE} or more."})
    blocks.append({"type": "text", "tone": "info",
                   "text": "Each finding shows k/n, its 90% confidence interval and the strength of the evidence against what "
                           "would happen by chance: «strong» (≥8 matches), «moderate» (≥5) or «hint». "
                           "Only repeated patterns are listed (usually in half of the matches or more)."})
    for kind, title in GROUPS:
        items = [f for f in ctx.findings if f["kind"] == kind]
        if not items:
            rows = [{"texto": "Nothing conclusive in this sample.", "evidencia": "", "fuerza": ""}]
        else:
            items.sort(key=sort_key)
            rows = [{"texto": f["text"], "evidencia": evidence_text(f), "fuerza": f.get("evidence") or ""} for f in items]
        blocks.append({"type": "table", "title": title, "n": ctx.n, "kind": kind,
                       "columns": [{"key": "texto", "label": ""}, {"key": "evidencia", "label": "Matches · CI90"},
                                   {"key": "fuerza", "label": "Evidence", "fmt": "evidence"}],
                       "rows": rows})
    return blocks


EVIDENCE_ORDER = {"strong": 0, "moderate": 1, "hint": 2, None: 3}


def sort_key(f):
    """Primero la evidencia más fuerte; dentro de cada nivel, el límite inferior más alto."""
    return (EVIDENCE_ORDER.get(f.get("evidence"), 3), -(f.get("lo") or 0))


def evidence_text(f):
    """«7/9 · CI90 45–94%» (o vacío si el hallazgo no es una proporción)."""
    if not f.get("total"):
        return ""
    return f"{f['support']}/{f['total']} · CI90 {round(100 * f['lo'])}–{round(100 * f['hi'])}%"
