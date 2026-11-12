"""Roles por héroe (tabla editable en roles.json) y cálculo del rol de un jugador."""
import json
import os
import re

from . import config

_DEFAULT_THRESHOLD = 0.25


def normalize(name):
    s = (name or "").lower()
    s = re.sub(r"^the\s+", "", s.strip())
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)


def load_table(path=None):
    path = path or config.ROLES_PATH
    if not os.path.exists(path):
        return {}, _DEFAULT_THRESHOLD
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("roles", {}), float(data.get("umbral_rol", _DEFAULT_THRESHOLD))


def hero_roles(table, hero_names):
    """{hero_id: [roles]} a partir de {hero_id: nombre}."""
    by_norm = {}
    for role, heroes in table.items():
        for h in heroes:
            by_norm.setdefault(normalize(h), []).append(role)
    return {hid: by_norm.get(normalize(n), []) for hid, n in hero_names.items()}


def player_roles(hero_matches, roles_by_hero, threshold=_DEFAULT_THRESHOLD):
    """hero_matches: {hero_id: partidas}. Devuelve (roles>=umbral, desglose ordenado [(rol, cuota)])."""
    share = {}
    total = 0
    for hid, n in hero_matches.items():
        if n <= 0:
            continue
        total += n
        rs = roles_by_hero.get(hid) or ["Sin rol"]
        for r in rs:
            share[r] = share.get(r, 0) + n / len(rs)
    if not total:
        return [], []
    breakdown = sorted(((r, v / total) for r, v in share.items()), key=lambda t: -t[1])
    main = [r for r, v in breakdown if v >= threshold and r != "Sin rol"]
    return main, breakdown


def breakdown_text(breakdown, min_share=0.01):
    return " · ".join(f"{r.lower()} {round(v * 100)}%" for r, v in breakdown if v >= min_share)
