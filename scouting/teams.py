"""Lectura de equipos.txt.

Formato (una línea por jugador): uno o varios IDs y después el nombre del equipo.
    35187362 Buff Enjoyers
    483770846, 802747733 Buff Enjoyers
Las líneas vacías y las que empiezan por # se ignoran.
"""
import os
import re

from .ids import to_account_id

_TOKEN = re.compile(r"\s*([^\s,;]+)[\s,;]*")


def parse_line(line):
    """Devuelve (lista_de_account_ids, nombre_equipo) o None."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    ids = []
    pos = 0
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            break
        aid = to_account_id(m.group(1))
        if aid is None:
            break
        ids.append(aid)
        pos = m.end()
    team = s[pos:].strip()
    if not ids or not team:
        return None
    return ids, team


def parse_text(text):
    rows, errors = [], []
    for n, line in enumerate(text.splitlines(), 1):
        r = parse_line(line)
        if r:
            rows.append(r)
        elif line.strip() and not line.strip().startswith("#"):
            errors.append(f"line {n}: cannot parse \"{line.strip()}\"")
    return rows, errors


def read_file(path):
    if not os.path.exists(path):
        return [], []
    with open(path, encoding="utf-8-sig") as f:
        return parse_text(f.read())
