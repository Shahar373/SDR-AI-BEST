#!/usr/bin/env python3
"""
Session management skill.

Usage:
  session.py start  --data '{"location":..., "antennas":[...], "goal":...}'
  session.py status
  session.py end    [--summary "..."]

All commands print JSON to stdout. Exit 0 on success, 1 on error.

Dry-run (validation only, no disk write):
  session.py start --data '...' --dry-run
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from lib import session_store, db
from lib.env import ensure_dirs


def _validate_antenna(ant: dict) -> str | None:
    required = {"name", "min_hz", "max_hz"}
    missing = required - set(ant.keys())
    if missing:
        return f"antenna missing fields: {missing}"
    try:
        lo = float(ant["min_hz"])
        hi = float(ant["max_hz"])
        if lo < 0 or hi <= lo:
            return "antenna min_hz must be < max_hz and both non-negative"
    except (TypeError, ValueError):
        return "antenna min_hz/max_hz must be numeric"
    return None


def cmd_start(args) -> None:
    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        sys.exit(1)

    errors = []
    if not data.get("location"):
        errors.append("location is required")
    antennas = data.get("antennas", [])
    if not antennas:
        errors.append("at least one antenna is required")
    for ant in antennas:
        err = _validate_antenna(ant)
        if err:
            errors.append(err)
    if not data.get("goal"):
        errors.append("goal is required")

    if errors:
        print(json.dumps({"error": "validation_failed", "details": errors}))
        sys.exit(1)

    session = {
        "session_id": str(uuid.uuid4()),
        "location": data["location"],
        "antennas": antennas,
        "goal": data["goal"],
        "methods": data.get("methods", []),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    # Compute covered range from antenna union
    covered = []
    for ant in antennas:
        covered.append({"name": ant["name"],
                         "min_hz": float(ant["min_hz"]),
                         "max_hz": float(ant["max_hz"])})
    session["antenna_coverage"] = covered

    if args.dry_run:
        print(json.dumps({"status": "dry_run_ok", "session": session}, ensure_ascii=False, indent=2))
        return

    ensure_dirs()
    session_store.write(session)

    # Persist to knowledge base
    conn = db.get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, location, antennas_json, goal, started_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (session["session_id"], session["location"],
         json.dumps(antennas, ensure_ascii=False),
         session["goal"], session["started_at"])
    )
    conn.commit()
    conn.close()

    # Build coverage advisory
    all_min = min(float(a["min_hz"]) for a in antennas)
    all_max = max(float(a["max_hz"]) for a in antennas)
    advisory = (f"Antenna coverage: {all_min/1e6:.3f}–{all_max/1e6:.3f} MHz. "
                f"Frequencies outside this range will be flagged as possibly antenna-limited.")

    print(json.dumps({
        "status": "session_started",
        "session_id": session["session_id"],
        "location": session["location"],
        "goal": session["goal"],
        "antenna_coverage_advisory": advisory,
        "antennas": covered,
        "started_at": session["started_at"],
    }, ensure_ascii=False, indent=2))


def cmd_status(args) -> None:
    session = session_store.read()
    if not session:
        print(json.dumps({"status": "no_active_session"}))
        return

    started = datetime.fromisoformat(session["started_at"])
    duration_s = (datetime.now(timezone.utc) - started).total_seconds()
    print(json.dumps({
        "status": "active",
        "session_id": session["session_id"],
        "location": session["location"],
        "goal": session["goal"],
        "duration_minutes": round(duration_s / 60, 1),
        "antennas": session.get("antennas", []),
    }, ensure_ascii=False, indent=2))


def cmd_end(args) -> None:
    session = session_store.read()
    if not session:
        print(json.dumps({"status": "no_active_session"}))
        return

    ended_at = datetime.now(timezone.utc).isoformat()
    summary = args.summary or "(no summary provided)"

    conn = db.get_conn()
    conn.execute(
        "UPDATE sessions SET ended_at=?, summary=? WHERE id=?",
        (ended_at, summary, session["session_id"])
    )
    conn.commit()
    conn.close()

    session_store.clear()
    print(json.dumps({
        "status": "session_ended",
        "session_id": session["session_id"],
        "ended_at": ended_at,
        "summary": summary,
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Session management")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("--data", required=True,
                          help='JSON: {"location":..., "antennas":[...], "goal":...}')
    p_start.add_argument("--dry-run", action="store_true")

    sub.add_parser("status")

    p_end = sub.add_parser("end")
    p_end.add_argument("--summary", default="")

    args = parser.parse_args()
    if args.command == "start":
        cmd_start(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "end":
        cmd_end(args)


if __name__ == "__main__":
    main()
