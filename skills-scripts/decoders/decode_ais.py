#!/usr/bin/env python3
"""
Decode AIS vessel tracking on 161.975 / 162.025 MHz via AIS-catcher.

AIS-catcher natively supports SDRplay; we invoke it with SoapySDR device
selection so it works with SoapySDRPlay3 as well.

Usage:
  python3 decoders/decode_ais.py --duration-secs 120
  python3 decoders/decode_ais.py --dry-run [--fixture fixtures/ais_fixture.json]
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sanitize_rf_text import sanitize_value
from lib.rf_lock_module import acquire as rf_acquire, RFLockTimeout

BINARY           = "AIS-catcher"
DEFAULT_DURATION = 120
_FIXTURE_PATH    = Path(__file__).parent.parent.parent / "fixtures" / "ais_fixture.json"

# AIS-catcher JSON output fields we care about
_STR_FIELDS  = {"mmsi", "shipname", "callsign", "destination", "shiptype"}
_NUM_FIELDS  = {"lat", "lon", "sog", "cog", "heading", "status"}


def _check_binary() -> str | None:
    if shutil.which(BINARY) is None:
        return (f"'{BINARY}' not found. Build from source: "
                "https://github.com/jvde-github/AIS-catcher")
    return None


def _parse_vessel(msg: dict) -> dict:
    """Extract and sanitize fields from one AIS-catcher JSON message."""
    vessel: dict = {}
    for k in _STR_FIELDS:
        if k in msg:
            vessel[k] = sanitize_value(msg[k])
    for k in _NUM_FIELDS:
        if k in msg:
            vessel[k] = msg[k]
    # msg_type is always an integer (AIS message type 1–27)
    try:
        vessel["msg_type"] = int(msg.get("type", 0))
    except (TypeError, ValueError):
        vessel["msg_type"] = None
    return vessel


def _run_live(duration_secs: int) -> dict:
    err = _check_binary()
    if err:
        return {"error": "binary_missing", "binary": BINARY, "tip": err}

    # Device selector: SDRplay-specific SoapySDR driver string.
    # Override with SDR_SOAPY_DEVICE env var if the Pi has multiple SDR devices.
    import os as _os
    device = _os.environ.get("SDR_SOAPY_DEVICE", "driver=sdrplay")
    # -o 4 = JSON output to stdout, one object per line
    # -v 0 = suppress informational chatter
    cmd = [BINARY, "-d", device, "-o", "4", "-v", "0"]

    vessels: list[dict] = []
    stderr_lines: list[str] = []

    try:
        with rf_acquire(BINARY, timeout=30):
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
                text=True,
            )
            deadline = time.monotonic() + duration_secs
            # Read JSON lines until time is up
            proc.stdout.fileno()  # ensure it's a real fd
            import select
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                rlist, _, _ = select.select([proc.stdout], [], [], min(1.0, remaining))
                if rlist:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            if isinstance(msg, dict) and "mmsi" in msg:
                                vessels.append(_parse_vessel(msg))
                        except json.JSONDecodeError:
                            pass
                if proc.poll() is not None:
                    break

            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    except RFLockTimeout as exc:
        return {"error": "rf_lock_timeout", "detail": str(exc)}

    # Deduplicate by MMSI (keep most recent entry per vessel)
    seen: dict = {}
    for v in vessels:
        mmsi = v.get("mmsi")
        if mmsi:
            seen[mmsi] = v
    unique_vessels = list(seen.values())

    return {
        "decoder":        "decode_ais",
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "duration_secs":  duration_secs,
        "vessel_count":   len(unique_vessels),
        "vessels":        unique_vessels,
    }


def main():
    ap = argparse.ArgumentParser(description="AIS decoder (AIS-catcher)")
    ap.add_argument("--duration-secs", type=int, default=DEFAULT_DURATION)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fixture", default=None)
    args = ap.parse_args()

    if args.dry_run:
        p = Path(args.fixture) if args.fixture else _FIXTURE_PATH
        try:
            print(p.read_text())
        except FileNotFoundError:
            print(json.dumps({"error": "fixture_not_found", "path": str(p)}))
            sys.exit(1)
        return

    result = _run_live(args.duration_secs)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
