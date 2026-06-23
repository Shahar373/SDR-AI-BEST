#!/usr/bin/env python3
"""
Generate a PNG spectrogram (waterfall) artifact for a frequency span.

Live: captures IQ, computes an STFT, renders a waterfall PNG to ARTIFACTS_DIR,
and records an artifacts row. Can also render from an existing IQ file.

Usage:
  spectrogram.py --center-hz 433920000 --span-hz 2000000 --secs 10
  spectrogram.py --iq-path capture.cf32 --sample-rate-hz 200000 --center-hz 433920000
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import dsp, db, rf_lock_module
from lib.env import ARTIFACTS_DIR, ensure_dirs


def _render(iq, fs: float, center_hz: float, out_path: Path, title: str) -> None:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import signal as ss

    nperseg = min(1024, max(64, len(iq) // 50))
    f, t, Sxx = ss.spectrogram(iq, fs=fs, nperseg=nperseg,
                               return_onesided=False, scaling="spectrum")
    f = np.fft.fftshift(f)
    Sxx = np.fft.fftshift(Sxx, axes=0)
    Sxx_db = 10 * np.log10(Sxx + 1e-30)

    fig, ax = plt.subplots(figsize=(10, 6))
    extent = [t[0], t[-1], (center_hz + f[0]) / 1e6, (center_hz + f[-1]) / 1e6]
    im = ax.imshow(Sxx_db, aspect="auto", origin="lower", extent=extent, cmap="viridis")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (MHz)")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="Power (dB)")
    fig.tight_layout()
    fig.savefig(str(out_path), dpi=100)
    plt.close(fig)


def _capture_live(center_hz: float, span_hz: float, secs: float):
    import SoapySDR
    import numpy as np

    sdr = SoapySDR.Device({"driver": "SoapySDRPlay3"})
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, float(span_hz))
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, float(center_hz))
    sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, True)
    stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(stream)

    n_samples = int(span_hz * secs)
    buf = np.zeros(n_samples, dtype=np.complex64)
    got = 0
    while got < n_samples:
        chunk = np.zeros(min(1 << 16, n_samples - got), dtype=np.complex64)
        sr = sdr.readStream(stream, [chunk], len(chunk))
        if sr.ret <= 0:
            break
        buf[got:got + sr.ret] = chunk[:sr.ret]
        got += sr.ret
    sdr.deactivateStream(stream)
    sdr.closeStream(stream)
    return buf[:got]


def main():
    ap = argparse.ArgumentParser(description="Spectrogram waterfall PNG")
    ap.add_argument("--center-hz", type=float, required=True)
    ap.add_argument("--span-hz", type=float, default=2_000_000)
    ap.add_argument("--secs", type=float, default=5.0)
    ap.add_argument("--iq-path", default=None)
    ap.add_argument("--sample-rate-hz", type=float, default=None)
    args = ap.parse_args()

    ensure_dirs()
    spec_id = str(uuid.uuid4())
    out_path = ARTIFACTS_DIR / f"spectrogram-{spec_id}.png"
    title = f"{args.center_hz/1e6:.3f} MHz ± {args.span_hz/2e6:.2f} MHz"

    if args.iq_path:
        fs = args.sample_rate_hz or args.span_hz
        iq = dsp.load_iq(args.iq_path)
    else:
        try:
            import SoapySDR  # noqa: F401
        except ImportError as exc:
            print(json.dumps({"error": "missing_dependency", "detail": str(exc)}))
            sys.exit(1)
        fs = args.span_hz
        with rf_lock_module.acquire("spectrogram", timeout=30):
            iq = _capture_live(args.center_hz, args.span_hz, args.secs)

    if len(iq) < 128:
        print(json.dumps({"error": "iq_too_short", "samples": int(len(iq))}))
        sys.exit(1)

    _render(iq, float(fs), args.center_hz, out_path, title)
    size = out_path.stat().st_size

    # Record artifact (observation_id NULL — linked later by catalog if relevant)
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO artifacts (id, observation_id, kind, path, size_bytes, created_at) "
        "VALUES (?, NULL, 'spectrogram', ?, ?, ?)",
        (spec_id, str(out_path), size, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

    print(json.dumps({
        "spectrogram_id": spec_id,
        "path": str(out_path),
        "center_hz": args.center_hz,
        "span_hz": args.span_hz,
        "size_bytes": size,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
