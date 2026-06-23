"""SQLite connection factory for the spectrum knowledge base."""
import sqlite3
from .env import DB_PATH, ensure_dirs


def get_conn(row_factory: bool = True) -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH))
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
