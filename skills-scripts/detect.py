#!/usr/bin/env python3
"""
Discrete-signal finder — finer resolution than sweep, scoped to one span.

Live: tunes to center_hz, captures a short window at span_hz sample rate,
computes a high-resolution PSD, groups contiguous bins into signals, and
classifies each as continuous vs burst from its envelope.

Dry-run: replays a fixture (no hardware).

Usage:
  detect.py --center-hz 433920000 --span-hz 2000000 --secs 5
  detect.py --dry-run --fixture fixtures/detect_fixture.json
  detect.py --dry-run
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import session_store, dsp, rf_lock_module, sdr_io
from lib.env import ensure_dirs

DETECT_THRESHOLD_DB = 10  # dB above noise floor to call a signal


def _synthetic_fixture() -> dict:
    return {
        "detect_id": "dry-run",
        "session_id": "dry-run",
        "center_hz": 433920000,
        "span_hz": 2000000,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signals": [
            {"center_hz": 433920000, "bandwidth_hz": 100000, "kind": "burst",
             "snr": 22.4, "occupancy": 0.18},
        ],
    }


def _detect_live(center_hz: float, span_hz: float, secs: float) -> list[dict]:
    sdr, stream = sdr_io.open_rx(center_hz, float(span_hz), agc=True)
    try:
        buf = sdr_io.read_samples(sdr, stream, int(span_hz * secs), float(span_hz))
    finally:
        sdr_io.close(sdr, stream)

    freqs, psd = dsp.welch_psd(buf, float(span_hz), nfft=8192)
    psd_db = dsp.to_db(psd)
    threshold = dsp.noise_floor(psd_db, pct=30) + DETECT_THRESHOLD_DB
    grouped = dsp.group_signals(psd_db, freqs, center_hz, threshold)

    # Classify each grouped signal as burst/continuous using the full-band envelope
    kind, _, _, duty = dsp.burst_structure(buf, float(span_hz))
    nf = dsp.noise_floor(psd_db, pct=30)
    for sig in grouped:
        sig["kind"] = "continuous" if duty > 0.6 else kind
        sig["snr"] = round(sig["peak_dbfs"] - nf, 1)
    return grouped


def main():
    ap = argparse.ArgumentParser(description="Discrete-signal finder")
    ap.add_argument("--center-hz", type=float)
    ap.add_argument("--span-hz", type=float, default=2_000_000)
    ap.add_argument("--secs", type=float, default=3.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fixture", default=None)
    args = ap.parse_args()

    if args.dry_run:
        result = (json.loads(Path(args.fixture).read_text())
                  if args.fixture else _synthetic_fixture())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.center_hz is None:
        print(json.dumps({"error": "missing_arg", "detail": "--center-hz required in live mode"}))
        sys.exit(1)

    session = session_store.require()
    ensure_dirs()

    with rf_lock_module.acquire("detect", timeout=30):
        signals = _detect_live(args.center_hz, args.span_hz, args.secs)

    print(json.dumps({
        "detect_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "center_hz": args.center_hz,
        "span_hz": args.span_hz,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
