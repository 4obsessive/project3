"""SQLite: esquema y conexión. Los campos manuales viven en su propia tabla y nunca se tocan al actualizar."""
import os
import sqlite3
import threading
import time

from . import config

DB_PATH = os.path.join(config.DATA_DIR, "scouting.db")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);

-- Un jugador = una persona. Puede tener varias cuentas.
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    display_name TEXT,
    primary_account_id INTEGER,
    first_seen INTEGER NOT NULL,
    in_leaderboard INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(id),
    source TEXT NOT NULL,              -- leaderboard | team | manual
    steam_name TEXT,
    badge INTEGER,
    steam_checked INTEGER
);
CREATE INDEX IF NOT EXISTS ix_accounts_player ON accounts(player_id);

-- Campos manuales (no se sobrescriben nunca en las actualizaciones)
CREATE TABLE IF NOT EXISTS manual (
    player_id INTEGER PRIMARY KEY REFERENCES players(id),
    twitter TEXT, twitch TEXT, discord TEXT,
    adult TEXT NOT NULL DEFAULT 'desconocido',      -- sí | no | desconocido
    status TEXT NOT NULL DEFAULT 'pendiente',
    notes TEXT, team TEXT,
    updated_at INTEGER
);

-- Resolución nombre de leaderboard -> cuenta elegida entre possible_account_ids
CREATE TABLE IF NOT EXISTS lb_resolution (
    name TEXT NOT NULL,
    candidates TEXT NOT NULL,         -- ids ordenados separados por comas
    account_id INTEGER,
    method TEXT,
    n_candidates INTEGER,
    resolved_at INTEGER,
    PRIMARY KEY (name, candidates)
);

CREATE TABLE IF NOT EXISTS lb_snapshots (
    id INTEGER PRIMARY KEY,
    leaderboard_id INTEGER,
    region TEXT NOT NULL,
    season TEXT,
    taken_at INTEGER NOT NULL,
    n_entries INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lb_entries (
    snapshot_id INTEGER NOT NULL REFERENCES lb_snapshots(id),
    rank INTEGER NOT NULL,
    account_name TEXT,
    account_id INTEGER,
    player_id INTEGER,
    top_hero_ids TEXT
);
CREATE INDEX IF NOT EXISTS ix_lbe_snap ON lb_entries(snapshot_id);
CREATE INDEX IF NOT EXISTS ix_lbe_player ON lb_entries(player_id);

-- Stats del periodo (últimos N días) por cuenta y héroe; se reemplazan en cada actualización
CREATE TABLE IF NOT EXISTS hero_stats (
    account_id INTEGER NOT NULL,
    hero_id INTEGER NOT NULL,
    matches INTEGER, wins INTEGER, kills INTEGER, deaths INTEGER, assists INTEGER,
    player_damage INTEGER, damage_taken INTEGER, boss_damage INTEGER, creep_damage INTEGER,
    obj_damage_per_min REAL, damage_per_min REAL, networth_per_min REAL, accuracy REAL,
    time_played INTEGER, last_played INTEGER,
    PRIMARY KEY (account_id, hero_id)
);
CREATE TABLE IF NOT EXISTS stats_fetched (account_id INTEGER PRIMARY KEY, fetched_at INTEGER);

-- Historial (una fila por jugador y actualización) para tendencias
CREATE TABLE IF NOT EXISTS stats_history (
    player_id INTEGER NOT NULL,
    taken_at INTEGER NOT NULL,
    matches INTEGER, wins INTEGER, kills INTEGER, deaths INTEGER, assists INTEGER,
    rank INTEGER,
    PRIMARY KEY (player_id, taken_at)
);

CREATE TABLE IF NOT EXISTS mates_cache (account_id INTEGER PRIMARY KEY, fetched_at INTEGER, data TEXT);

-- Plantillas de equipo (equipos.txt). line_no agrupa cuentas del mismo jugador.
CREATE TABLE IF NOT EXISTS team_rosters (
    team TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    line_no INTEGER,
    PRIMARY KEY (team, account_id)
);

-- Resúmenes materializados tras cada actualización (JSON por jugador)
CREATE TABLE IF NOT EXISTS summaries (player_id INTEGER PRIMARY KEY, data TEXT NOT NULL);

-- Partidas (JSON completo comprimido en data/matches; aquí lo extraído)
CREATE TABLE IF NOT EXISTS matches (
    match_id INTEGER PRIMARY KEY,
    start_time INTEGER, duration_s INTEGER, winning_team INTEGER,
    game_mode INTEGER, match_mode INTEGER,
    source TEXT, stored_at INTEGER
);
CREATE TABLE IF NOT EXISTS match_players (
    match_id INTEGER NOT NULL, player_slot INTEGER NOT NULL, team INTEGER,
    account_id INTEGER, hero_id INTEGER, kills INTEGER, deaths INTEGER, assists INTEGER,
    net_worth INTEGER, last_hits INTEGER, denies INTEGER, level INTEGER,
    PRIMARY KEY (match_id, player_slot)
);
CREATE INDEX IF NOT EXISTS ix_mp_account ON match_players(account_id);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,             -- running | done | error | interrupted
    step TEXT, progress TEXT, message TEXT,
    started_at INTEGER, finished_at INTEGER
);

-- Cola del demo (Midboss/KOTH): una fila por partida
CREATE TABLE IF NOT EXISTS demo_jobs (
    match_id INTEGER PRIMARY KEY,
    state TEXT NOT NULL,             -- pending | done | nodemo | error
    summary TEXT, error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_try INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER
);
"""

_local = threading.local()
_init_lock = threading.Lock()
_initialized = set()


def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    with _init_lock:
        if path not in _initialized:
            con.executescript(SCHEMA)
            _initialized.add(path)
    return con


def get(path=None):
    """Conexión por hilo."""
    key = path or DB_PATH
    cons = getattr(_local, "cons", None)
    if cons is None:
        cons = _local.cons = {}
    if key not in cons:
        cons[key] = connect(key)
    return cons[key]


def kv_get(con, key, default=None):
    r = con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def kv_set(con, key, value):
    con.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def now():
    return int(time.time())
