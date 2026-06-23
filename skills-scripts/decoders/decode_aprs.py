#!/usr/bin/env python3
"""
Decode APRS on 144.800 MHz (Israel standard) via SoapySDR FM demod → multimon-ng.

Pipeline (live):
  SoapySDR IQ capture → Python FM discriminator → resample to 22050 Hz
  → pipe s16le to multimon-ng → parse APRS packet strings.

All decoded text passes through sanitize_rf_text before returning.

Usage:
  python3 decoders/decode_aprs.py --duration-secs 120
  python3 decoders/decode_aprs.py --dry-run [--fixture fixtures/aprs_fixture.json]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sanitize_rf_text import sanitize_value
from lib.rf_lock_module import acquire as rf_acquire, RFLockTimeout

BINARY           = "multimon-ng"
DEFAULT_DURATION = 120
APRS_FREQ_HZ     = 144_800_000
CAPTURE_BW_HZ    = 250_000      # 250 kHz capture bandwidth
AUDIO_RATE_HZ    = 22_050       # multimon-ng default
_FIXTURE_PATH    = Path(__file__).parent.parent.parent / "fixtures" / "aprs_fixture.json"

# Match multimon-ng APRS output lines: "APRS: <raw packet>"
_APRS_RE = re.compile(r"^APRS:\s*(.+)$", re.MULTILINE)


def _check_binary() -> str | None:
    if shutil.which(BINARY) is None:
        return f"'{BINARY}' not found. Install: sudo apt install multimon-ng"
    return None


def _fm_demod_to_s16le(iq, fs: float, out_rate: float) -> bytes:
    """FM discriminator → resample → s16le bytes (in-memory, no disk I/O)."""
    import numpy as np
    from lib.dsp import instantaneous_freq
    from math import gcd
    from scipy.signal import resample_poly

    ifreq = instantaneous_freq(iq, fs).astype(np.float32)
    # Normalize to [-1, 1] by half the carrier bandwidth
    half_bw = fs / 2.0
    ifreq = np.clip(ifreq / half_bw, -1.0, 1.0)

    g = gcd(int(out_rate), int(fs))
    audio = resample_poly(ifreq, int(out_rate) // g, int(fs) // g)

    # Final normalize
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio /= peak

    return (audio * 32767).clip(-32768, 32767).astype(np.int16).tobytes()


def _parse_aprs_packet(raw: str) -> dict:
    """Minimal APRS packet parser — returns sanitized fields."""
    raw = raw.strip()
    packet: dict = {"raw": sanitize_value(raw)}

    # Source callsign (before >)
    m = re.match(r"^([A-Z0-9-]+)>", raw)
    if m:
        packet["source"] = sanitize_value(m.group(1))

    # Position: !DDMM.MMN/DDDMM.MME
    m = re.search(r"!(\d{2})(\d{2}\.\d+)([NS])[/\\|](\d{3})(\d{2}\.\d+)([EW])", raw)
    if m:
        lat_d, lat_m, lat_h, lon_d, lon_m, lon_h = m.groups()
        lat = (int(lat_d) + float(lat_m) / 60.0) * (1 if lat_h == "N" else -1)
        lon = (int(lon_d) + float(lon_m) / 60.0) * (1 if lon_h == "E" else -1)
        packet["lat"] = round(lat, 5)
        packet["lon"] = round(lon, 5)

    # Comment / info field (after the data type indicator)
    m = re.search(r"[>:,][^:]*:(.+)$", raw)
    if m:
        packet["info"] = sanitize_value(m.group(1))

    return packet


def _run_live(duration_secs: int) -> dict:
    err = _check_binary()
    if err:
        return {"error": "binary_missing", "binary": BINARY, "tip": err}

    try:
        import SoapySDR  # noqa: F401
    except ImportError as exc:
        return {"error": "missing_dependency", "detail": str(exc)}

    from lib import sdr_io

    packets: list[dict] = []
    try:
        with rf_acquire(BINARY, timeout=30):
            sdr, stream = sdr_io.open_rx(APRS_FREQ_HZ, float(CAPTURE_BW_HZ), agc=True)
            n_samples = int(CAPTURE_BW_HZ * duration_secs)
            iq = sdr_io.read_samples(sdr, stream, n_samples, float(CAPTURE_BW_HZ))
            sdr_io.close(sdr, stream)
    except RFLockTimeout as exc:
        return {"error": "rf_lock_timeout", "detail": str(exc)}

    raw_audio = _fm_demod_to_s16le(iq, float(CAPTURE_BW_HZ), float(AUDIO_RATE_HZ))

    try:
        result = subprocess.run(
            [BINARY, "-t", "raw", "-s", "-a", "APRS", "-"],
            input=raw_audio,
            capture_output=True,
            timeout=max(30, len(raw_audio) // AUDIO_RATE_HZ // 2 + 10),
        )
        output = result.stdout.decode(errors="replace")
    except subprocess.TimeoutExpired:
        return {"error": "decoder_timeout", "binary": BINARY}
    except FileNotFoundError:
        return {"error": "binary_missing", "binary": BINARY}

    for m in _APRS_RE.finditer(output):
        packets.append(_parse_aprs_packet(m.group(1)))

    return {
        "decoder":       "decode_aprs",
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "duration_secs": duration_secs,
        "center_hz":     APRS_FREQ_HZ,
        "packet_count":  len(packets),
        "packets":       packets,
    }


def main():
    ap = argparse.ArgumentParser(description="APRS decoder (multimon-ng)")
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
