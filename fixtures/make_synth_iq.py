#!/usr/bin/env python3
"""
Generate synthetic IQ captures (.cf32) so the survey loop
characterize→classify→identify→catalog can be tested end-to-end with NO
hardware. Writes into fixtures/iq_samples/.

Signals produced:
  fm_tone.cf32     continuous narrowband FM (audio-modulated carrier)
  fsk_burst.cf32   bursty 2-FSK (433 MHz ISM-style remote)
  bpsk.cf32        continuous BPSK
  cw.cf32          continuous CW carrier

Usage:
  python3 fixtures/make_synth_iq.py [--fs 200000] [--secs 1.0] [--snr-db 25]
"""
import argparse
import numpy as np
from pathlib import Path

OUT_DIR = Path(__file__).parent / "iq_samples"


def _awgn(sig: np.ndarray, snr_db: float) -> np.ndarray:
    sp = np.mean(np.abs(sig) ** 2) + 1e-30
    npow = sp / (10 ** (snr_db / 10))
    noise = np.sqrt(npow / 2) * (np.random.randn(len(sig)) + 1j * np.random.randn(len(sig)))
    return (sig + noise).astype(np.complex64)


def make_fm_tone(fs, secs, snr_db):
    n = int(fs * secs)
    t = np.arange(n) / fs
    audio = np.sin(2 * np.pi * 1000 * t)          # 1 kHz tone
    dev = 5000.0                                   # 5 kHz deviation → NFM
    phase = 2 * np.pi * dev * np.cumsum(audio) / fs
    sig = np.exp(1j * phase)
    return _awgn(sig, snr_db)


def make_fsk_burst(fs, secs, snr_db):
    n = int(fs * secs)
    baud = 4800.0
    sps = int(fs / baud)
    f_dev = 25000.0
    # Random bits
    nbits = n // sps
    bits = np.random.randint(0, 2, nbits)
    symbols = np.repeat(np.where(bits == 1, f_dev, -f_dev), sps)
    symbols = np.concatenate([symbols, np.zeros(n - len(symbols))])
    phase = 2 * np.pi * np.cumsum(symbols) / fs
    sig = np.exp(1j * phase)
    # Burst gating: 480 ms on, rest off, repeating
    env = np.zeros(n)
    on = int(0.10 * fs)
    period = int(0.30 * fs)
    for start in range(0, n, period):
        env[start:start + on] = 1.0
    sig = sig * env
    return _awgn(sig, snr_db)


def make_bpsk(fs, secs, snr_db):
    n = int(fs * secs)
    baud = 9600.0
    sps = int(fs / baud)
    nsym = n // sps
    bits = np.random.randint(0, 2, nsym) * 2 - 1   # ±1
    sig = np.repeat(bits, sps).astype(np.complex64)
    sig = np.concatenate([sig, np.zeros(n - len(sig), dtype=np.complex64)])
    return _awgn(sig, snr_db)


def make_cw(fs, secs, snr_db):
    n = int(fs * secs)
    t = np.arange(n) / fs
    sig = np.exp(1j * 2 * np.pi * 100 * t)         # 100 Hz offset carrier
    return _awgn(sig, snr_db)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fs", type=float, default=200_000)
    ap.add_argument("--secs", type=float, default=1.0)
    ap.add_argument("--snr-db", type=float, default=25)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    np.random.seed(args.seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    generators = {
        "fm_tone": make_fm_tone,
        "fsk_burst": make_fsk_burst,
        "bpsk": make_bpsk,
        "cw": make_cw,
    }
    written = []
    for name, fn in generators.items():
        sig = fn(args.fs, args.secs, args.snr_db)
        path = OUT_DIR / f"{name}.cf32"
        sig.astype(np.complex64).tofile(str(path))
        written.append({"name": name, "path": str(path),
                        "fs": args.fs, "samples": len(sig)})

    print(f"Wrote {len(written)} synthetic IQ files to {OUT_DIR} (fs={args.fs}, secs={args.secs})")
    for w in written:
        print(f"  {w['name']:12s} {w['samples']:>8d} samples → {w['path']}")


if __name__ == "__main__":
    main()
