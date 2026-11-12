"""Conclusiones generales a partir de los hallazgos que registran las demás métricas."""
from .. import SMALL_SAMPLE, metric

GROUPS = [
    ("strength", "Fortalezas"),
    ("weakness", "Debilidades"),
    ("pattern", "Patrones repetidos"),
    ("improve", "Qué mejorar"),
    ("opportunity", "Oportunidades tácticas"),
]


@metric("conclusiones", "Conclusiones generales", order=999)
def conclusiones(ctx):
    blocks = []
    if ctx.n == 0:
        return [{"type": "unavailable", "title": "Conclusiones", "reason": "No hay partidas con lado detectado."}]
    if ctx.n < SMALL_SAMPLE:
        blocks.append({"type": "text", "tone": "warning",
                       "text": f"Con {ctx.n} partidas las conclusiones son orientativas. Para hablar de patrones conviene llegar a {SMALL_SAMPLE} o más."})
    blocks.append({"type": "text", "tone": "info",
                   "text": "Cada hallazgo lleva k/n, su intervalo de confianza al 90 % y la fuerza de la evidencia frente a lo que "
                           "pasaría por azar: «fuerte» (≥8 partidas), «moderada» (≥5) o «indicio». "
                           "«Confirmado» = sale directamente de los datos; «interpretación» = lectura táctica de esos datos."})
    for kind, title in GROUPS:
        items = [f for f in ctx.findings if f["kind"] == kind]
        if not items:
            rows = [{"texto": "Nada concluyente en esta muestra.", "evidencia": "", "tipo": ""}]
        else:
            items.sort(key=sort_key)
            rows = [{"texto": f["text"], "evidencia": evidence_text(f), "fuerza": f.get("evidence") or "",
                     "tipo": "confirmado" if f["confirmed"] else "interpretación"} for f in items]
        blocks.append({"type": "table", "title": title, "n": ctx.n, "kind": kind,
                       "columns": [{"key": "texto", "label": ""}, {"key": "evidencia", "label": "Partidas · IC90"},
                                   {"key": "fuerza", "label": "Evidencia", "fmt": "evidence"}, {"key": "tipo", "label": "Tipo"}],
                       "rows": rows})
    return blocks


EVIDENCE_ORDER = {"fuerte": 0, "moderada": 1, "indicio": 2, None: 3}


def sort_key(f):
    """Primero la evidencia más fuerte; dentro de cada nivel, el límite inferior más alto."""
    return (EVIDENCE_ORDER.get(f.get("evidence"), 3), -(f.get("lo") or 0))


def evidence_text(f):
    """«7/9 · IC90 45–94%» (o vacío si el hallazgo no es una proporción)."""
    if not f.get("total"):
        return ""
    return f"{f['support']}/{f['total']} · IC90 {round(100 * f['lo'])}–{round(100 * f['hi'])}%"
