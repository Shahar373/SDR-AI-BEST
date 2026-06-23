#!/usr/bin/env python3
"""
Receive and decode a NOAA weather satellite APT image pass via satdump.

NOAA-15/18/19 transmit APT on 137.620 / 137.912 / 137.100 MHz.
A pass lasts ~15 minutes (900 s); the caller should schedule for a predicted
overhead pass.

Storage discipline: NOAA PNG images are large (~1–3 MB). We set
retain_until = now + NOAA_RETAIN_DAYS (default 30) so artifact_cleanup.py
deletes them automatically.

Usage:
  python3 decoders/capture_noaa.py --freq-hz 137912500 --duration-secs 900
  python3 decoders/capture_noaa.py --dry-run [--fixture fixtures/noaa_fixture.json]
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
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import db
from lib.rf_lock_module import acquire as rf_acquire, RFLockTimeout
from lib.env import ARTIFACTS_DIR, ensure_dirs

BINARY            = "satdump"
DEFAULT_FREQ_HZ   = 137_912_500     # NOAA-18 APT
DEFAULT_DURATION  = 900             # 15-minute pass
NOAA_RETAIN_DAYS  = int(os.environ.get("NOAA_RETAIN_DAYS", "30"))
_FIXTURE_PATH     = Path(__file__).parent.parent.parent / "fixtures" / "noaa_fixture.json"


def _check_binary() -> str | None:
    if shutil.which(BINARY) is None:
        return (f"'{BINARY}' not found. Build from "
                "https://github.com/SatDump/SatDump")
    return None


def _run_live(freq_hz: int, duration_secs: int) -> dict:
    err = _check_binary()
    if err:
        return {"error": "binary_missing", "binary": BINARY, "tip": err}

    ensure_dirs()
    cap_id = f"noaa-{int(time.time())}"
    tmpdir = tempfile.mkdtemp(prefix="satdump-")
    out_dir = Path(tmpdir)

    # satdump live pipeline: IQ source → APT decoder → PNG output
    cmd = [
        BINARY,
        "live",
        "NOAA_APT",              # pipeline name
        "baseband",              # output type
        "--source", "sdrplay",   # SDRplay RSP1B native source
        "--samplerate", "1000000",
        "--frequency", str(freq_hz),
        "--duration", str(duration_secs),
        "--output", str(out_dir),
        "--finish_processing",   # process after capture completes
    ]

    try:
        with rf_acquire(BINARY, timeout=30):
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
            )
            # satdump exits when --duration expires; we give it extra time for processing
            try:
                proc.wait(timeout=duration_secs + 120)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    proc.wait(timeout=15)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    except RFLockTimeout as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"error": "rf_lock_timeout", "detail": str(exc)}

    # Find the decoded PNG (satdump writes something like NOAA_APT/NOAA_APT_*.png)
    pngs = sorted(out_dir.rglob("*.png"), key=lambda p: p.stat().st_size, reverse=True)
    if not pngs:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {
            "error":       "no_image_produced",
            "decoder":     "capture_noaa",
            "freq_hz":     freq_hz,
            "duration_secs": duration_secs,
            "tip":         "Check satdump stderr. Weak signal or wrong frequency?",
        }

    # Move the largest PNG to ARTIFACTS_DIR with a datestamped name
    src_png = pngs[0]
    dest_name = f"noaa-apt-{cap_id}.png"
    dest_path = ARTIFACTS_DIR / dest_name
    shutil.move(str(src_png), str(dest_path))
    shutil.rmtree(tmpdir, ignore_errors=True)

    size_bytes = dest_path.stat().st_size
    now        = datetime.now(timezone.utc)
    retain_dt  = now + timedelta(days=NOAA_RETAIN_DAYS)

    # Register artifact with retain_until so cleanup runs automatically
    conn = db.get_conn()
    import uuid
    conn.execute(
        "INSERT INTO artifacts (id, observation_id, kind, path, size_bytes, "
        "created_at, retain_until) VALUES (?,NULL,'noaa_apt',?,?,?,?)",
        (str(uuid.uuid4()), str(dest_path), size_bytes,
         now.isoformat(), retain_dt.isoformat()),
    )
    conn.commit()
    conn.close()

    return {
        "decoder":       "capture_noaa",
        "timestamp":     now.isoformat(),
        "freq_hz":       freq_hz,
        "duration_secs": duration_secs,
        "image_path":    str(dest_path),
        "size_bytes":    size_bytes,
        "retain_until":  retain_dt.isoformat(),
        "retain_days":   NOAA_RETAIN_DAYS,
    }


def main():
    ap = argparse.ArgumentParser(description="NOAA APT image capture (satdump)")
    ap.add_argument("--freq-hz", type=int, default=DEFAULT_FREQ_HZ)
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

    result = _run_live(args.freq_hz, args.duration_secs)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
