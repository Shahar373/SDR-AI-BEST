#!/usr/bin/env python3
"""
Decode ADS-B 1090 MHz Mode S Extended Squitter via dump1090-fa.

dump1090-fa talks directly to the SDRplay RSP1B via its native --device-type
sdrplay driver (no SoapySDR needed for this decoder).

Usage:
  python3 decoders/decode_adsb.py --duration-secs 60
  python3 decoders/decode_adsb.py --dry-run [--fixture fixtures/adsb_fixture.json]
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sanitize_rf_text import sanitize_value
from lib.rf_lock_module import acquire as rf_acquire, RFLockTimeout

BINARY          = "dump1090-fa"
DEFAULT_DURATION = 60
ADSB_FREQ_HZ    = 1_090_000_000
_FIXTURE_PATH   = Path(__file__).parent.parent.parent / "fixtures" / "adsb_fixture.json"


def _check_binary() -> str | None:
    path = shutil.which(BINARY)
    if path is None:
        return (f"Binary '{BINARY}' not found. "
                "Install: sudo apt install dump1090-fa  or build from source.")
    return None


def _run_live(duration_secs: int) -> dict:
    err = _check_binary()
    if err:
        return {"error": "binary_missing", "binary": BINARY, "tip": err}

    tmpdir = tempfile.mkdtemp(prefix="dump1090-")
    aircraft_json = Path(tmpdir) / "aircraft.json"

    cmd = [
        BINARY,
        "--device-type", "sdrplay",
        "--write-json", tmpdir,
        "--write-json-every", "1",
        "--quiet",
    ]

    result: dict = {}
    try:
        with rf_acquire(BINARY, timeout=30):
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
            )
            time.sleep(duration_secs)
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

        aircraft = []
        if aircraft_json.exists():
            try:
                data = json.loads(aircraft_json.read_text())
                for ac in data.get("aircraft", []):
                    aircraft.append({
                        "icao":     sanitize_value(ac.get("hex")),
                        "callsign": sanitize_value((ac.get("flight") or "").strip() or None),
                        "lat":      ac.get("lat"),
                        "lon":      ac.get("lon"),
                        "alt_ft":   ac.get("alt_baro"),
                        "speed_kt": ac.get("gs"),
                        "squawk":   sanitize_value(ac.get("squawk")),
                        "messages": ac.get("messages", 0),
                    })
            except Exception as exc:
                result = {"error": "parse_failed", "detail": str(exc)}

        if not result:
            result = {
                "decoder":         "decode_adsb",
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "duration_secs":   duration_secs,
                "aircraft_count":  len(aircraft),
                "aircraft":        aircraft,
            }
    except RFLockTimeout as exc:
        result = {"error": "rf_lock_timeout", "detail": str(exc)}
    finally:
        import shutil as _sh
        _sh.rmtree(tmpdir, ignore_errors=True)

    return result


def main():
    ap = argparse.ArgumentParser(description="ADS-B decoder (dump1090-fa)")
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
