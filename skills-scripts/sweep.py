#!/usr/bin/env python3
"""
Wideband occupancy sweep.

Live mode: sweeps start_hz..stop_hz in CHUNK_HZ chunks using SoapySDR/RSP1B.
Dry-run:   reads from a fixture file (no hardware required).

Output JSON:
  {
    "sweep_id": "...",
    "session_id": "...",
    "start_hz": ..., "stop_hz": ...,
    "timestamp": "...",
    "antenna_warnings": [...],
    "signals": [
      {"center_hz": ..., "bandwidth_hz": ..., "peak_dbfs": ..., "occupancy": 0.0-1.0}
    ]
  }

Usage:
  sweep.py [--start-hz N] [--stop-hz N] [--chunk-hz N] [--dwell SECS]
  sweep.py --dry-run --fixture fixtures/sweep_fixture.json
  sweep.py --dry-run                  # uses built-in synthetic fixture
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import session_store, db
from lib import rf_lock_module
from lib import dsp
from lib.env import SIGNAL_REF_DB, ensure_dirs

# RSP1B receivable range
RSP1B_MIN_HZ = 1_000        # 1 kHz
RSP1B_MAX_HZ = 2_000_000_000  # 2 GHz
CHUNK_HZ     = 10_000_000   # 10 MHz max instantaneous BW

# Minimum signal amplitude to report (dBFS above noise floor heuristic)
SIGNAL_THRESHOLD_DB = 15


def _synthetic_fixture() -> dict:
    """Built-in fixture so --dry-run works without any fixture file."""
    return {
        "sweep_id": "dry-run-fixture",
        "session_id": "dry-run",
        "start_hz": 88_000_000,
        "stop_hz": 108_000_000,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "antenna_warnings": [],
        "signals": [
            {"center_hz": 88_400_000,  "bandwidth_hz": 200_000, "peak_dbfs": -42.1, "occupancy": 0.98},
            {"center_hz": 92_100_000,  "bandwidth_hz": 200_000, "peak_dbfs": -38.7, "occupancy": 0.97},
            {"center_hz": 98_000_000,  "bandwidth_hz": 200_000, "peak_dbfs": -35.2, "occupancy": 0.99},
            {"center_hz": 103_600_000, "bandwidth_hz": 200_000, "peak_dbfs": -44.0, "occupancy": 0.95},
        ],
    }


def _check_antenna_coverage(start_hz: float, stop_hz: float, session: dict) -> list[str]:
    warnings = []
    antennas = session.get("antennas", [])
    if not antennas:
        return ["no antenna data in session — coverage unknown"]

    covered_min = min(float(a["min_hz"]) for a in antennas)
    covered_max = max(float(a["max_hz"]) for a in antennas)

    if start_hz < covered_min:
        warnings.append(
            f"Sweep starts at {start_hz/1e6:.3f} MHz but lowest antenna coverage is "
            f"{covered_min/1e6:.3f} MHz — signals below {covered_min/1e6:.3f} MHz may "
            f"be absent due to antenna, not absence of signal."
        )
    if stop_hz > covered_max:
        warnings.append(
            f"Sweep ends at {stop_hz/1e6:.3f} MHz but highest antenna coverage is "
            f"{covered_max/1e6:.3f} MHz — signals above {covered_max/1e6:.3f} MHz may "
            f"be absent due to antenna, not absence of signal."
        )
    return warnings


def _sweep_live(start_hz: float, stop_hz: float, chunk_hz: int, dwell: float) -> list[dict]:
    """Perform a real SoapySDR power sweep and return detected signals."""
    try:
        import SoapySDR
        import numpy as np
    except ImportError as exc:
        print(json.dumps({"error": "missing_dependency", "detail": str(exc),
                          "tip": "Run provision/install.sh to install SoapySDR"}))
        sys.exit(1)

    signals = []
    sdr = SoapySDR.Device({"driver": "SoapySDRPlay3"})
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, float(chunk_hz))
    sdr.setAntenna(SoapySDR.SOAPY_SDR_RX, 0, "Antenna C")  # wideband port on RSP1B
    sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, True)        # AGC on

    stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(stream)

    freq = start_hz
    while freq < stop_hz:
        center = freq + chunk_hz / 2
        sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, center)

        n_samples = int(chunk_hz * dwell)
        buf = np.zeros(n_samples, dtype=np.complex64)
        sr = sdr.readStream(stream, [buf], n_samples)
        if sr.ret <= 0:
            freq += chunk_hz
            continue

        # Power spectrum + contiguous-bin signal grouping (shared lib.dsp)
        buf = buf[:sr.ret]
        freqs, psd = dsp.welch_psd(buf, float(chunk_hz), nfft=4096)
        psd_dbfs = dsp.to_db(psd)
        threshold = dsp.noise_floor(psd_dbfs, pct=30) + SIGNAL_THRESHOLD_DB
        signals.extend(dsp.group_signals(psd_dbfs, freqs, center, threshold))

        freq += chunk_hz

    sdr.deactivateStream(stream)
    sdr.closeStream(stream)
    return signals


def _upsert_occupancy(conn, sweep_id: str, session_id: str, signals: list[dict], timestamp: str):
    for sig in signals:
        conn.execute(
            "INSERT INTO occupancy (id, session_id, center_hz, bandwidth_hz, peak_dbfs, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id,
             sig["center_hz"], sig["bandwidth_hz"], sig["peak_dbfs"], timestamp)
        )


def main():
    parser = argparse.ArgumentParser(description="Wideband occupancy sweep")
    parser.add_argument("--start-hz",  type=float, default=RSP1B_MIN_HZ)
    parser.add_argument("--stop-hz",   type=float, default=RSP1B_MAX_HZ)
    parser.add_argument("--chunk-hz",  type=int,   default=CHUNK_HZ)
    parser.add_argument("--dwell",     type=float, default=1.0,
                        help="Seconds to dwell per chunk (live mode)")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--fixture",   default=None,
                        help="Path to fixture JSON (--dry-run only)")
    args = parser.parse_args()

    if args.dry_run:
        if args.fixture:
            result = json.loads(Path(args.fixture).read_text())
        else:
            result = _synthetic_fixture()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Live mode
    session = session_store.require()
    ensure_dirs()

    warnings = _check_antenna_coverage(args.start_hz, args.stop_hz, session)
    timestamp = datetime.now(timezone.utc).isoformat()
    sweep_id = str(uuid.uuid4())

    with rf_lock_module.acquire("sweep", timeout=30):
        signals = _sweep_live(args.start_hz, args.stop_hz, args.chunk_hz, args.dwell)

    result = {
        "sweep_id": sweep_id,
        "session_id": session["session_id"],
        "start_hz": args.start_hz,
        "stop_hz": args.stop_hz,
        "timestamp": timestamp,
        "antenna_warnings": warnings,
        "signals": signals,
    }

    conn = db.get_conn()
    _upsert_occupancy(conn, sweep_id, session["session_id"], signals, timestamp)
    conn.commit()
    conn.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
