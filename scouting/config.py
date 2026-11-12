"""Configuración: config.json en la raíz del proyecto (se crea con valores por defecto)."""
import json
import os
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
STATIC_DIR = os.path.join(ROOT, "static")
CONFIG_PATH = os.path.join(ROOT, "config.json")
TEAMS_PATH = os.path.join(ROOT, "equipos.txt")
ROLES_PATH = os.path.join(ROOT, "roles.json")
OBJECTIVES_PATH = os.path.join(ROOT, "objetivos.json")

DEFAULTS = {
    # Región de la leaderboard: Europe, Asia, NAmerica, SAmerica, Oceania
    "region": "Europe",
    # Leaderboards adicionales (temporadas anteriores) que también aportan jugadores.
    # 1001 = Beta Season 1 (1000 jugadores en Europa). La temporada actual se usa siempre.
    "extra_leaderboard_ids": [1001],
    "update_interval_hours": 24,
    "stats_days": 30,
    "api_key": "",
    "batch_size": 50,
    "host": "127.0.0.1",
    "port": 8000,
    "open_browser": True,
}

_lock = threading.Lock()


def load():
    with _lock:
        cfg = dict(DEFAULTS)
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except (OSError, ValueError) as e:
                print(f"[config] No se pudo leer config.json ({e}); uso valores por defecto.")
        else:
            save(cfg, _locked=True)
        return cfg


def save(cfg, _locked=False):
    def _write():
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)

    if _locked:
        _write()
    else:
        with _lock:
            _write()


def update(changes):
    cfg = load()
    for k, v in changes.items():
        if k in DEFAULTS:
            cfg[k] = v
    save(cfg)
    return cfg
