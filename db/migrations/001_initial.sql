-- Migration 001: initial schema (same as schema.sql baseline)
-- Applied automatically by db_init.py if schema_migrations.version < 1.

-- sessions
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    location     TEXT NOT NULL,
    antennas_json TEXT NOT NULL,
    goal         TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    summary      TEXT
);

-- occupancy
CREATE TABLE IF NOT EXISTS occupancy (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    center_hz    REAL NOT NULL,
    bandwidth_hz REAL NOT NULL,
    peak_dbfs    REAL NOT NULL,
    timestamp    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_occupancy_session ON occupancy(session_id);
CREATE INDEX IF NOT EXISTS idx_occupancy_center  ON occupancy(center_hz);
CREATE INDEX IF NOT EXISTS idx_occupancy_ts      ON occupancy(timestamp);

-- signals
CREATE TABLE IF NOT EXISTS signals (
    id                      TEXT PRIMARY KEY,
    emitter_key             TEXT UNIQUE NOT NULL,
    first_seen              TEXT NOT NULL,
    last_seen               TEXT NOT NULL,
    center_hz               REAL NOT NULL,
    bandwidth_hz            REAL NOT NULL,
    modulation_family       TEXT,
    baud_estimate           REAL,
    kind                    TEXT,
    identity_top            TEXT,
    identity_score          REAL,
    identity_candidates_json TEXT,
    status                  TEXT NOT NULL DEFAULT 'unknown',
    observation_count       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_signals_center ON signals(center_hz);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);

-- observations
CREATE TABLE IF NOT EXISTS observations (
    id                   TEXT PRIMARY KEY,
    signal_id            TEXT NOT NULL,
    session_id           TEXT NOT NULL,
    timestamp            TEXT NOT NULL,
    snr                  REAL,
    feature_vector_json  TEXT,
    artifact_path        TEXT,
    decoder_output_json  TEXT
);
CREATE INDEX IF NOT EXISTS idx_observations_signal  ON observations(signal_id);
CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_observations_ts      ON observations(timestamp);

-- artifacts
CREATE TABLE IF NOT EXISTS artifacts (
    id             TEXT PRIMARY KEY,
    observation_id TEXT,
    kind           TEXT NOT NULL,
    path           TEXT NOT NULL,
    size_bytes     INTEGER,
    created_at     TEXT NOT NULL,
    retain_until   TEXT
);

-- migrations tracker
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_migrations VALUES (1, datetime('now'));
