"""
RF device arbiter — Python module for use inside skill scripts.

Usage:
    from lib.rf_lock_module import acquire

    with acquire("sweep.py", timeout=30):
        # radio work here — flock is held for the duration
        ...

The flock is released when the context exits (including on exceptions).
"""
import fcntl
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .env import RF_LOCK_FILE, RF_LOCK_INFO_FILE, ensure_dirs


class RFLockTimeout(RuntimeError):
    pass


@contextmanager
def acquire(holder: str, timeout: int = 30):
    ensure_dirs()
    RF_LOCK_FILE.touch(exist_ok=True)

    fd = open(RF_LOCK_FILE, "w")
    deadline = time.monotonic() + timeout

    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                fd.close()
                current = _read_info()
                raise RFLockTimeout(
                    f"Could not acquire RF lock within {timeout}s. "
                    f"Held by: {current.get('holder','?')} "
                    f"(pid {current.get('pid','?')}) "
                    f"since {current.get('acquired_at','?')}"
                )
            time.sleep(0.2)

    info = {
        "pid": os.getpid(),
        "holder": holder,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    RF_LOCK_INFO_FILE.write_text(json.dumps(info))

    try:
        yield info
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()
        try:
            RF_LOCK_INFO_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def status() -> dict:
    if not RF_LOCK_FILE.exists():
        return {"status": "free"}
    # Try a non-blocking exclusive lock to see if the file is held.
    # Open append ("a") not write ("w") so probing never truncates a file
    # another process is actively holding.
    try:
        with open(RF_LOCK_FILE, "a") as fd:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                return {"status": "free"}
            except BlockingIOError:
                pass
    except FileNotFoundError:
        return {"status": "free"}

    info = _read_info()
    return {
        "status": "locked",
        "held_by": info.get("holder", "unknown"),
        "pid": info.get("pid"),
        "acquired_at": info.get("acquired_at"),
    }


def force_release() -> dict:
    info = _read_info()
    RF_LOCK_INFO_FILE.unlink(missing_ok=True)
    RF_LOCK_FILE.unlink(missing_ok=True)
    return {"status": "released", "was_held_by": info.get("holder", "unknown")}


def _read_info() -> dict:
    try:
        return json.loads(RF_LOCK_INFO_FILE.read_text())
    except Exception:
        return {}
