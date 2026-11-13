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
-- Stats de los últimos 7 días (forma reciente); se reemplazan en cada actualización
CREATE TABLE IF NOT EXISTS hero_stats_7d (
    account_id INTEGER NOT NULL, hero_id INTEGER NOT NULL, matches INTEGER, wins INTEGER,
    PRIMARY KEY (account_id, hero_id)
);
-- Perfiles de Steam (nombre y avatar) de cualquier cuenta vista: seguidas y jugadores de partidas
CREATE TABLE IF NOT EXISTS steam_profiles (
    account_id INTEGER PRIMARY KEY, personaname TEXT, avatar TEXT, countrycode TEXT, fetched_at INTEGER
);
-- Badge/rango por actualización (una fila por cuenta y actualización)
CREATE TABLE IF NOT EXISTS badge_history (
    account_id INTEGER NOT NULL, taken_at INTEGER NOT NULL, badge INTEGER, flat_progress REAL,
    PRIMARY KEY (account_id, taken_at)
);
-- Historial de partidas por cuenta (caché de /match-history, 60 días)
CREATE TABLE IF NOT EXISTS player_matches (
    account_id INTEGER NOT NULL, match_id INTEGER NOT NULL, start_time INTEGER, hero_id INTEGER, won INTEGER,
    k INTEGER, d INTEGER, a INTEGER, net_worth INTEGER, last_hits INTEGER, duration_s INTEGER,
    match_mode INTEGER, badge INTEGER, ranked_delta INTEGER,
    PRIMARY KEY (account_id, match_id)
);
CREATE INDEX IF NOT EXISTS ix_pm_account_time ON player_matches(account_id, start_time);
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
    raw TEXT,                        -- resultados crudos de las consultas (JSON), para rehacer el resumen
    attempts INTEGER NOT NULL DEFAULT 0,
    next_try INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER
);
"""

# Columnas añadidas después de la primera versión: (tabla, columna, tipo). Se añaden con ALTER TABLE
# si faltan, así una base existente se migra sin perder datos.
MIGRATIONS = [
    ("hero_stats", "last_hits_per_min", "REAL"),
    ("hero_stats", "denies_per_min", "REAL"),
    ("hero_stats", "damage_taken_per_min", "REAL"),
    ("hero_stats", "deaths_per_min", "REAL"),
    ("hero_stats", "crit_shot_rate", "REAL"),
    ("hero_stats", "mvp_rank_counts", "TEXT"),
    ("hero_stats", "mvp_rated_matches", "INTEGER"),
    ("demo_jobs", "raw", "TEXT"),    # resultados crudos del demo, para rehacer el resumen
]

HERO_STATS_COLS = [
    # (columna, campo de la API)
    ("account_id", "account_id"), ("hero_id", "hero_id"), ("matches", "matches_played"), ("wins", "wins"),
    ("kills", "kills"), ("deaths", "deaths"), ("assists", "assists"), ("player_damage", "total_player_damage"),
    ("damage_taken", "total_player_damage_taken"), ("boss_damage", "total_boss_damage"), ("creep_damage", "total_creep_damage"),
    ("obj_damage_per_min", "obj_damage_per_min"), ("damage_per_min", "damage_per_min"), ("networth_per_min", "networth_per_min"),
    ("accuracy", "accuracy"), ("time_played", "time_played"), ("last_played", "last_played"),
    ("last_hits_per_min", "last_hits_per_min"), ("denies_per_min", "denies_per_min"),
    ("damage_taken_per_min", "damage_taken_per_min"), ("deaths_per_min", "deaths_per_min"),
    ("crit_shot_rate", "crit_shot_rate"), ("mvp_rank_counts", "mvp_rank_counts"), ("mvp_rated_matches", "mvp_rated_matches"),
]


def migrate(con):
    for table, col, typ in MIGRATIONS:
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        if col not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    con.commit()


def insert_hero_stats(con, rows):
    """Inserta filas de /v1/players/hero-stats (sin commit: el llamador abre la transacción)."""
    import json as _json
    cols = ",".join(c for c, _ in HERO_STATS_COLS)
    q = f"INSERT OR REPLACE INTO hero_stats({cols}) VALUES({','.join('?' * len(HERO_STATS_COLS))})"
    for r in rows:
        vals = []
        for c, f in HERO_STATS_COLS:
            v = r.get(f)
            if c == "mvp_rank_counts" and v is not None and not isinstance(v, str):
                v = _json.dumps(v)
            vals.append(v)
        con.execute(q, vals)


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
            migrate(con)
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
