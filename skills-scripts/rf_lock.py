#!/usr/bin/env python3
"""
RF lock CLI — for status checks, force-release, and integration testing.

Usage:
  rf_lock.py status
  rf_lock.py release --force
  rf_lock.py test-block [--duration SECS]   # hold the lock for N seconds (testing only)

Real radio skills use lib.rf_lock_module.acquire() as a context manager
so the flock is held in-process for the full duration of the radio work.
"""
import argparse
import json
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from lib import rf_lock_module


def main():
    parser = argparse.ArgumentParser(description="RF lock CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    p_rel = sub.add_parser("release")
    p_rel.add_argument("--force", action="store_true", required=True,
                       help="Force-release a stale lock (use only when holder is dead)")

    p_test = sub.add_parser("test-block")
    p_test.add_argument("--duration", type=float, default=5.0,
                        help="Seconds to hold the lock")
    p_test.add_argument("--holder", default="test-block")

    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(rf_lock_module.status(), indent=2))

    elif args.command == "release":
        result = rf_lock_module.force_release()
        print(json.dumps(result, indent=2))

    elif args.command == "test-block":
        try:
            with rf_lock_module.acquire(args.holder, timeout=5):
                print(json.dumps({"status": "acquired", "holder": args.holder,
                                  "will_hold_secs": args.duration}))
                sys.stdout.flush()
                time.sleep(args.duration)
                print(json.dumps({"status": "releasing"}))
        except rf_lock_module.RFLockTimeout as exc:
            print(json.dumps({"error": "lock_timeout", "detail": str(exc)}))
            sys.exit(1)


if __name__ == "__main__":
    main()
