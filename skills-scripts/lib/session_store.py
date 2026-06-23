"""Session store: read/write the active session JSON file."""
import json
from typing import Optional
from .env import SESSION_FILE, ensure_dirs


def read() -> Optional[dict]:
    if not SESSION_FILE.exists():
        return None
    try:
        return json.loads(SESSION_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def write(data: dict) -> None:
    ensure_dirs()
    SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def clear() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def require() -> dict:
    """Return the active session or raise SystemExit with JSON error."""
    import sys
    session = read()
    if not session:
        print(json.dumps({"error": "no_active_session",
                          "message": "Start a session first with: session start ..."}))
        sys.exit(1)
    return session
