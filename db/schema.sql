-- Spectrum Knowledge Base schema
-- All timestamps are ISO-8601 UTC strings.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Work sessions ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    location     TEXT NOT NULL,
    antennas_json TEXT NOT NULL,   -- JSON array of antenna descriptors
    goal         TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    summary      TEXT
);

-- ── Occupancy snapshots ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS occupancy (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    center_hz    REAL NOT NULL,
    bandwidth_hz REAL NOT NULL,
    peak_dbfs    REAL NOT NULL,
    timestamp    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_occupancy_session  ON occupancy(session_id);
CREATE INDEX IF NOT EXISTS idx_occupancy_center   ON occupancy(center_hz);
CREATE INDEX IF NOT EXISTS idx_occupancy_ts       ON occupancy(timestamp);

-- ── Signal catalog (one row per emitter) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    id                      TEXT PRIMARY KEY,
    emitter_key             TEXT UNIQUE NOT NULL,  -- derived: round(center_hz,-3)||"_"||modulation
    first_seen              TEXT NOT NULL,
    last_seen               TEXT NOT NULL,
    center_hz               REAL NOT NULL,
    bandwidth_hz            REAL NOT NULL,
    modulation_family       TEXT,   -- AM|FM|PSK|FSK|OFDM|CW|UNKNOWN|...
    baud_estimate           REAL,
    kind                    TEXT,   -- continuous|burst|intermittent
    identity_top            TEXT,   -- best candidate name, e.g. "FM Broadcast"
    identity_score          REAL,   -- 0.0-1.0 confidence
    identity_candidates_json TEXT,  -- JSON array of {name, score, notes}
    status                  TEXT NOT NULL DEFAULT 'unknown',  -- identified|unknown|tracking
    observation_count       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_signals_center ON signals(center_hz);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);

-- ── Per-observation detail ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS observations (
    id                   TEXT PRIMARY KEY,
    signal_id            TEXT NOT NULL REFERENCES signals(id),
    session_id           TEXT NOT NULL REFERENCES sessions(id),
    timestamp            TEXT NOT NULL,
    snr                  REAL,
    feature_vector_json  TEXT,  -- JSON object from characterize.py
    artifact_path        TEXT,  -- path to IQ/spectrogram artifact (if any)
    decoder_output_json  TEXT   -- JSON from decode_* scripts (sanitized, untrusted-tagged)
);
CREATE INDEX IF NOT EXISTS idx_observations_signal    ON observations(signal_id);
CREATE INDEX IF NOT EXISTS idx_observations_session   ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_observations_ts        ON observations(timestamp);

-- ── Artifacts table ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS artifacts (
    id             TEXT PRIMARY KEY,
    observation_id TEXT REFERENCES observations(id),
    kind           TEXT NOT NULL,  -- spectrogram|iq_capture|waterfall|article
    path           TEXT NOT NULL,
    size_bytes     INTEGER,
    created_at     TEXT NOT NULL,
    retain_until   TEXT            -- NULL = keep; ISO-8601 = delete after
);

-- ── Schema version ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_migrations VALUES (1, datetime('now'));
