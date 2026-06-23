"""SQLite connection factory for the spectrum knowledge base."""
import sqlite3
from .env import DB_PATH, SCHEMA_FILE, ensure_dirs


def get_conn(row_factory: bool = True) -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    # Lazy schema init: if the knowledge base hasn't been created yet (fresh
    # data dir, or SDR_DATA_DIR changed since provisioning), apply schema.sql
    # so callers never hit "no such table". FK enforcement is enabled AFTER
    # init so the executescript itself isn't blocked.
    has_signals = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='signals'"
    ).fetchone()
    if not has_signals and SCHEMA_FILE.exists():
        conn.executescript(SCHEMA_FILE.read_text())
        conn.commit()

    conn.execute("PRAGMA foreign_keys=ON")
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn
