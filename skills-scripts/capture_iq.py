#!/usr/bin/env python3
"""
Short IQ capture to ramdisk for characterization.

Hard caps: duration clamped to SDR_IQ_MAX_SECS; aborts if projected size
exceeds SDR_IQ_MAX_MB. Curiosity budget: at most SDR_MAX_IQ_CAPTURES_PER_CYCLE
captures per cycle (counter file in RUN_DIR, reset by --reset-budget).

Writes <SDR_IQ_DIR>/capture-<id>.cf32 plus a JSON sidecar so characterize
can resolve a capture by id.

Usage:
  capture_iq.py --center-hz 433920000 --span-hz 200000 --secs 5 [--retain]
  capture_iq.py --reset-budget       # reset the per-cycle counter (start of a sweep cycle)
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import session_store, rf_lock_module, sdr_io
from lib.env import (SDR_IQ_DIR, SDR_IQ_MAX_SECS, SDR_IQ_MAX_MB,
                     SDR_MAX_IQ_CAPTURES_PER_CYCLE, RUN_DIR, ensure_dirs)

CYCLE_COUNTER = RUN_DIR / "iq_cycle_count"
BYTES_PER_SAMPLE = 8  # complex64


def _read_counter() -> int:
    try:
        return int(CYCLE_COUNTER.read_text().strip())
    except Exception:
        return 0


def _write_counter(n: int) -> None:
    ensure_dirs()
    CYCLE_COUNTER.write_text(str(n))


def _capture_live(center_hz: float, span_hz: float, secs: float, out_path: Path) -> dict:
    sdr, stream = sdr_io.open_rx(center_hz, float(span_hz), agc=True)
    try:
        buf = sdr_io.read_samples(sdr, stream, int(span_hz * secs), float(span_hz))
    finally:
        sdr_io.close(sdr, stream)

    buf.astype("complex64").tofile(str(out_path))
    return {"samples": len(buf), "size_bytes": len(buf) * BYTES_PER_SAMPLE}


def main():
    ap = argparse.ArgumentParser(description="Short IQ capture to ramdisk")
    ap.add_argument("--center-hz", type=float)
    ap.add_argument("--span-hz", type=float, default=200_000)
    ap.add_argument("--secs", type=float, default=2.0)
    ap.add_argument("--retain", action="store_true",
                    help="Keep the IQ file after characterize reads it")
    ap.add_argument("--reset-budget", action="store_true",
                    help="Reset the per-cycle curiosity counter and exit")
    args = ap.parse_args()

    if args.reset_budget:
        _write_counter(0)
        print(json.dumps({"status": "budget_reset",
                          "max_per_cycle": SDR_MAX_IQ_CAPTURES_PER_CYCLE}))
        return

    if args.center_hz is None:
        print(json.dumps({"error": "missing_arg", "detail": "--center-hz required"}))
        sys.exit(1)

    # Curiosity budget
    used = _read_counter()
    if used >= SDR_MAX_IQ_CAPTURES_PER_CYCLE:
        print(json.dumps({
            "error": "curiosity_budget_exceeded",
            "used": used,
            "max_per_cycle": SDR_MAX_IQ_CAPTURES_PER_CYCLE,
            "tip": "Defer this capture to the next cycle, or --reset-budget at cycle start.",
        }))
        sys.exit(1)

    # Duration + size caps
    secs = min(args.secs, SDR_IQ_MAX_SECS)
    projected_mb = (args.span_hz * secs * BYTES_PER_SAMPLE) / (1024 * 1024)
    if projected_mb > SDR_IQ_MAX_MB:
        print(json.dumps({
            "error": "size_cap_exceeded",
            "projected_mb": round(projected_mb, 1),
            "max_mb": SDR_IQ_MAX_MB,
            "tip": "Reduce --span-hz or --secs.",
        }))
        sys.exit(1)

    session = session_store.require()
    ensure_dirs()
    SDR_IQ_DIR.mkdir(parents=True, exist_ok=True)

    capture_id = str(uuid.uuid4())
    out_path = SDR_IQ_DIR / f"capture-{capture_id}.cf32"
    sidecar = SDR_IQ_DIR / f"capture-{capture_id}.json"

    with rf_lock_module.acquire("capture_iq", timeout=30):
        info = _capture_live(args.center_hz, args.span_hz, secs, out_path)

    _write_counter(used + 1)

    meta = {
        "capture_id": capture_id,
        "session_id": session["session_id"],
        "path": str(out_path),
        "center_hz": args.center_hz,
        "sample_rate_hz": args.span_hz,
        "duration_secs": round(info["samples"] / args.span_hz, 3) if args.span_hz else secs,
        "size_mb": round(info["size_bytes"] / (1024 * 1024), 2),
        "retain": args.retain,
        "auto_delete_after": None if args.retain else "characterize",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "budget_used": used + 1,
        "budget_max": SDR_MAX_IQ_CAPTURES_PER_CYCLE,
    }
    sidecar.write_text(json.dumps(meta))
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
