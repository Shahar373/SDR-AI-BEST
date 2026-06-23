#!/usr/bin/env python3
"""
Decode ACARS aviation data-link messages via SoapySDR AM demod → acarsdec.

Pipeline (live):
  SoapySDR IQ capture at ACARS frequency → Python AM envelope demodulation
  → resample to 48 kHz → pipe s16le mono to acarsdec stdin → parse JSON output.

Standard ACARS frequencies (MHz): 129.125, 131.550, 131.725, 136.900.

Usage:
  python3 decoders/decode_acars.py [--freq-hz 131725000] --duration-secs 300
  python3 decoders/decode_acars.py --dry-run [--fixture fixtures/acars_fixture.json]
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sanitize_rf_text import sanitize_value
from lib.rf_lock_module import acquire as rf_acquire, RFLockTimeout

BINARY           = "acarsdec"
DEFAULT_DURATION = 300
DEFAULT_FREQ_HZ  = 131_725_000
CAPTURE_BW_HZ    = 96_000       # wide enough for ACARS AM signal (~8 kHz)
AUDIO_RATE_HZ    = 48_000
_FIXTURE_PATH    = Path(__file__).parent.parent.parent / "fixtures" / "acars_fixture.json"

_STR_FIELDS = {"reg", "flight", "msgno", "mode", "label", "block_id", "ack",
               "tail", "msg", "text", "dbi", "err"}


def _check_binary() -> str | None:
    if shutil.which(BINARY) is None:
        return (f"'{BINARY}' not found. Install: sudo apt install acarsdec "
                "or build from https://github.com/TLeconte/acarsdec")
    return None


def _am_demod_to_s16le(iq, fs: float, out_rate: float) -> bytes:
    """AM envelope detection → resample → s16le bytes (in-memory, no disk)."""
    import numpy as np
    from math import gcd
    from scipy.signal import resample_poly

    env = np.abs(iq).astype(np.float32)
    env -= env.mean()                   # remove DC

    g = gcd(int(out_rate), int(fs))
    audio = resample_poly(env, int(out_rate) // g, int(fs) // g)

    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio /= peak

    return (audio * 32767).clip(-32768, 32767).astype(np.int16).tobytes()


def _sanitize_msg(msg: dict) -> dict:
    out: dict = {}
    for k, v in msg.items():
        if k in _STR_FIELDS and v is not None:
            out[k] = sanitize_value(str(v))
        elif isinstance(v, (int, float)):
            out[k] = v
        elif v is not None:
            out[k] = sanitize_value(str(v))
    return out


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

    # acarsdec -r <rate> reads raw s16le from stdin when given '-'
    # -o 4 = JSON output; -g 0 = gain (handled by AGC above)
    cmd = [BINARY, "-o", "4", "-r", str(AUDIO_RATE_HZ), "-"]
    messages: list[dict] = []
    try:
        result = subprocess.run(
            cmd,
            input=raw_audio,
            capture_output=True,
            timeout=60,
        )
        for line in result.stdout.decode(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if isinstance(msg, dict):
                    messages.append(_sanitize_msg(msg))
            except json.JSONDecodeError:
                pass
    except subprocess.TimeoutExpired:
        return {"error": "decoder_timeout", "binary": BINARY}
    except FileNotFoundError:
        return {"error": "binary_missing", "binary": BINARY}

    return {
        "decoder":       "decode_acars",
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "freq_hz":       freq_hz,
        "duration_secs": duration_secs,
        "message_count": len(messages),
        "messages":      messages,
    }


def main():
    ap = argparse.ArgumentParser(description="ACARS decoder (acarsdec via AM demod)")
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
