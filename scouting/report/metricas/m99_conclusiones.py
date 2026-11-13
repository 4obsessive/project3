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
                   "text": "Solo se listan patrones que se repiten (normalmente en la mitad de las partidas o más)."})
    for kind, title in GROUPS:
        items = [f for f in ctx.findings if f["kind"] == kind]
        if not items:
            rows = [{"texto": "Nada concluyente en esta muestra.", "evidencia": ""}]
        else:
            items.sort(key=lambda f: -(f["support"] / f["total"]) if f.get("total") else 0)
            rows = [{"texto": f["text"], "evidencia": f"{f['support']}/{f['total']}" if f.get("total") else ""} for f in items]
        blocks.append({"type": "table", "title": title, "n": ctx.n,
                       "columns": [{"key": "texto", "label": ""}, {"key": "evidencia", "label": "Partidas"}],
                       "rows": rows})
    return blocks
