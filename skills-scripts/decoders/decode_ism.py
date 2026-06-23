#!/usr/bin/env python3
"""
Decode ISM-band devices (433/868 MHz) via rtl_433 with SoapySDR input.

rtl_433 with '-d :0' selects the first SoapySDR device (SDRplay RSP1B via
SoapySDRPlay3). It decodes hundreds of device types: weather stations, door
sensors, power meters, remote controls.

Usage:
  python3 decoders/decode_ism.py [--center-hz 433920000] --duration-secs 60
  python3 decoders/decode_ism.py --dry-run [--fixture fixtures/ism_fixture.json]
"""
import argparse
import json
import os
import re
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

BINARY           = "rtl_433"
DEFAULT_DURATION = 60
DEFAULT_CENTER   = 433_920_000
_FIXTURE_PATH    = Path(__file__).parent.parent.parent / "fixtures" / "ism_fixture.json"

_STR_FIELDS = {"model", "id", "channel", "subtype", "brand", "type_id"}


def _check_binary() -> str | None:
    if shutil.which(BINARY) is None:
        return f"'{BINARY}' not found. Install: sudo apt install rtl-433"
    return None


def _sanitize_device(msg: dict) -> dict:
    device: dict = {}
    for k, v in msg.items():
        if k in _STR_FIELDS:
            device[k] = sanitize_value(v)
        elif isinstance(v, (int, float)):
            device[k] = v
        elif isinstance(v, str):
            # Purely numeric/timestamp strings pass through; anything else is sanitized.
            # Pattern covers: numbers, decimals, signs, ISO timestamps (-, :, T, space).
            # Dash must be at end of character class to avoid accidental range.
            device[k] = v if re.fullmatch(r"[\d.+:T Z-]+", v) else sanitize_value(v)
        else:
            device[k] = v
    return device


def _run_live(center_hz: int, duration_secs: int) -> dict:
    err = _check_binary()
    if err:
        return {"error": "binary_missing", "binary": BINARY, "tip": err}

    # -d :0        = first SoapySDR device
    # -f <freq>    = center frequency
    # -F json      = JSON output to stdout
    # -T <secs>    = run for N seconds then exit
    # -M utc       = UTC timestamps
    cmd = [
        BINARY,
        "-d", ":0",
        "-f", str(int(center_hz)),
        "-F", "json",
        "-T", str(duration_secs),
        "-M", "utc",
        "-q",   # quiet — suppress status messages
    ]

    devices: list[dict] = []
    try:
        with rf_acquire(BINARY, timeout=30):
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
                text=True,
            )
            # rtl_433 self-terminates after -T seconds; we wait with a margin
            try:
                stdout, _ = proc.communicate(timeout=duration_secs + 15)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, _ = proc.communicate()

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if isinstance(msg, dict) and "model" in msg:
                    devices.append(_sanitize_device(msg))
            except json.JSONDecodeError:
                pass

    except RFLockTimeout as exc:
        return {"error": "rf_lock_timeout", "detail": str(exc)}

    return {
        "decoder":       "decode_ism",
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "center_hz":     center_hz,
        "duration_secs": duration_secs,
        "device_count":  len(devices),
        "devices":       devices,
    }


def main():
    ap = argparse.ArgumentParser(description="ISM decoder (rtl_433 + SoapySDR)")
    ap.add_argument("--center-hz", type=int, default=DEFAULT_CENTER)
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

    result = _run_live(args.center_hz, args.duration_secs)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
