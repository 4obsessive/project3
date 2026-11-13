"""KOTH / Rifts: los datos salen del demo de la partida (se completa en la tarea 4)."""
from .. import metric


@metric("koth", "KOTH / Rifts", order=50)
def koth(ctx):
    return [{"type": "unavailable", "title": "Eventos KOTH / Rifts",
             "reason": "La API de partidas no los trae: los datos de KOTH salen del demo de cada partida."}]
