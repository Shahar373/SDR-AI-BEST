#!/usr/bin/env python3
"""
Decode ACARS aviation data-link messages via SoapySDR AM demod → multimon-ng.

Pipeline (live):
  SoapySDR IQ capture at ACARS frequency → Python AM envelope demodulation
  → resample to 22050 Hz → pipe s16le mono to multimon-ng (-a ACARS) stdin
  → parse output.

acarsdec's '-r' flag sets RTL-SDR hardware sample rate and does NOT accept
raw PCM from stdin; multimon-ng is used here instead because it reliably reads
raw s16le from stdin in ACARS mode.

Standard ACARS VHF frequencies (MHz): 129.125, 131.550, 131.725, 136.900.

Usage:
  python3 decoders/decode_acars.py [--freq-hz 131725000] --duration-secs 300
  python3 decoders/decode_acars.py --dry-run [--fixture fixtures/acars_fixture.json]
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
DEFAULT_DURATION = 300
DEFAULT_FREQ_HZ  = 131_725_000
CAPTURE_BW_HZ    = 96_000       # wide enough for ACARS AM signal (~8 kHz)
AUDIO_RATE_HZ    = 22_050       # multimon-ng raw input rate
_FIXTURE_PATH    = Path(__file__).parent.parent.parent / "fixtures" / "acars_fixture.json"

# multimon-ng ACARS output: "ACARS: <fields>"
_ACARS_LINE = re.compile(r"^ACARS:\s*(.+)$", re.MULTILINE)
# Field patterns within an ACARS line
_FIELD_RE   = re.compile(r"(\w+)=(\S+)")


def _check_binary() -> str | None:
    if shutil.which(BINARY) is None:
        return f"'{BINARY}' not found. Install: sudo apt install multimon-ng"
    return None


def _am_demod_to_s16le(iq, fs: float, out_rate: float) -> bytes:
    """AM envelope detection → resample → s16le bytes (in-memory, no disk I/O)."""
    import numpy as np
    from math import gcd
    from scipy.signal import butter, sosfiltfilt, resample_poly

    env = np.abs(iq).astype(np.float64)
    env -= env.mean()

    # Low-pass filter at 5 kHz (ACARS audio bandwidth ~2.4 kHz) before resampling
    lpf_cutoff = min(5000.0 / (fs / 2.0), 0.95)
    sos = butter(4, lpf_cutoff, btype="low", output="sos")
    env = sosfiltfilt(sos, env)

    g = gcd(int(out_rate), int(fs))
    audio = resample_poly(env, int(out_rate) // g, int(fs) // g)

    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio /= peak

    return (audio * 32767).clip(-32768, 32767).astype(np.int16).tobytes()


def _parse_acars_line(raw: str) -> dict:
    """Extract key fields from a multimon-ng ACARS output line."""
    msg: dict = {"raw": sanitize_value(raw)}
    for m in _FIELD_RE.finditer(raw):
        key, val = m.group(1), m.group(2)
        key = key.lower()
        if key in {"reg", "flight", "label", "blk", "msg_no", "mode"}:
            msg[key] = sanitize_value(val)
        elif key == "msg":
            # msg= is followed by the rest of the line
            rest = raw[m.start(2):]
            msg["text"] = sanitize_value(rest)
            break
    return msg


def _run_live(freq_hz: int, duration_secs: int) -> dict:
    err = _check_binary()
    if err:
        return {"error": "binary_missing", "binary": BINARY, "tip": err}

    try:
        import SoapySDR  # noqa: F401
    except ImportError as exc:
        return {"error": "missing_dependency", "detail": str(exc)}

    from lib import sdr_io

    try:
        with rf_acquire(BINARY, timeout=30):
            sdr, stream = sdr_io.open_rx(freq_hz, float(CAPTURE_BW_HZ), agc=True)
            n_samples = int(CAPTURE_BW_HZ * duration_secs)
            iq = sdr_io.read_samples(sdr, stream, n_samples, float(CAPTURE_BW_HZ))
            sdr_io.close(sdr, stream)
    except RFLockTimeout as exc:
        return {"error": "rf_lock_timeout", "detail": str(exc)}

    raw_audio = _am_demod_to_s16le(iq, float(CAPTURE_BW_HZ), float(AUDIO_RATE_HZ))

    audio_secs = len(raw_audio) // 2 // AUDIO_RATE_HZ
    messages: list[dict] = []
    try:
        result = subprocess.run(
            [BINARY, "-t", "raw", "-a", "ACARS", "-"],
            input=raw_audio,
            capture_output=True,
            timeout=max(30, audio_secs + 15),
        )
        output = result.stdout.decode(errors="replace")
    except subprocess.TimeoutExpired:
        return {"error": "decoder_timeout", "binary": BINARY}
    except FileNotFoundError:
        return {"error": "binary_missing", "binary": BINARY}

    for m in _ACARS_LINE.finditer(output):
        messages.append(_parse_acars_line(m.group(1)))

    return {
        "decoder":       "decode_acars",
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "freq_hz":       freq_hz,
        "duration_secs": duration_secs,
        "message_count": len(messages),
        "messages":      messages,
    }


def main():
    ap = argparse.ArgumentParser(description="ACARS decoder (AM demod → multimon-ng)")
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
