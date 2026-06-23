#!/usr/bin/env python3
"""
Delete expired artifacts and optionally purge old uncapped ones.

Run from cron (daily, off-peak) or on-demand. Safe to run multiple times —
already-deleted files are silently skipped.

Usage:
  artifact_cleanup.py                         # delete only retain_until-expired
  artifact_cleanup.py --older-than-days 90    # also delete anything older than N days
  artifact_cleanup.py --dry-run               # show what would be deleted
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import db


def main():
    ap = argparse.ArgumentParser(description="Delete expired SDR artifacts")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be deleted without deleting")
    ap.add_argument("--older-than-days", type=int, default=None,
                    help="Also purge artifacts older than N days (ignores retain_until)")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    conn = db.get_conn()

    # Collect expired rows (retain_until set and in the past)
    expired = conn.execute(
        "SELECT id, path, kind, size_bytes, retain_until, created_at FROM artifacts "
        "WHERE retain_until IS NOT NULL AND retain_until <= ?",
        (now_iso,),
    ).fetchall()

    # Optionally collect uncapped old rows
    old: list = []
    if args.older_than_days is not None:
        cutoff = (now - timedelta(days=args.older_than_days)).isoformat()
        old = conn.execute(
            "SELECT id, path, kind, size_bytes, retain_until, created_at FROM artifacts "
            "WHERE created_at <= ? AND (retain_until IS NULL OR retain_until > ?)",
            (cutoff, now_iso),
        ).fetchall()

    to_delete = list(expired) + list(old)
    deleted_files = 0
    deleted_rows  = 0
    freed_bytes   = 0
    skipped_files = 0

    for row in to_delete:
        p = Path(row["path"])
        size = row["size_bytes"] or 0

        if p.exists():
            if args.dry_run:
                deleted_files += 1
                freed_bytes += size
            else:
                try:
                    p.unlink()
                    deleted_files += 1
                    freed_bytes += size
                except OSError:
                    # Can't delete the file (permission/NFS/etc.) — skip this
                    # row entirely; do NOT remove the DB record so the next run
                    # will retry.
                    skipped_files += 1
                    continue
        else:
            # File already gone (deleted by another process or previous partial run).
            # Still remove the orphan DB row; count the space as previously freed.
            freed_bytes += size

        if not args.dry_run:
            conn.execute("DELETE FROM artifacts WHERE id = ?", (row["id"],))
        deleted_rows += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(json.dumps({
        "status":           "dry_run" if args.dry_run else "ok",
        "artifacts_deleted": deleted_rows,
        "files_deleted":     deleted_files,
        "files_skipped":     skipped_files,
        "freed_bytes":       freed_bytes,
        "freed_mb":          round(freed_bytes / 1024 / 1024, 2),
        "timestamp":         now_iso,
    }, indent=2))


if __name__ == "__main__":
    main()
