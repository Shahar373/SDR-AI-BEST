#!/usr/bin/env python3
"""
Blind DSP feature extraction — the heart of the survey loop.

Given an IQ capture (by id or path), estimate modulation family, bandwidth,
symbol rate, burst structure, and confidence WITHOUT being told what the
signal is. Produces the feature_vector consumed by classify_signal/identify.

Usage:
  characterize.py --capture-id CAPTURE_ID
  characterize.py --iq-path /dev/shm/sdr-iq/capture-X.cf32 --sample-rate-hz 200000
  characterize.py --dry-run --fixture fixtures/characterize_fixture.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import dsp
from lib.env import SDR_IQ_DIR


def _resolve_capture(capture_id: str):
    sidecar = SDR_IQ_DIR / f"capture-{capture_id}.json"
    if not sidecar.exists():
        print(json.dumps({"error": "capture_not_found", "capture_id": capture_id}))
        sys.exit(1)
    meta = json.loads(sidecar.read_text())
    return Path(meta["path"]), float(meta["sample_rate_hz"]), float(meta["center_hz"]), meta


def _classify_modulation(iq, fs, freqs, psd_lin, psd_signal, bw) -> tuple[str, float, dict]:
    """
    Heuristic blind modulation-family estimate.

    Features are computed on the *active* (above-threshold) samples so burst
    gating does not masquerade as amplitude modulation, and frequency-spread
    measures are taken relative to the occupied bandwidth rather than fs.
    Robust percentiles are used throughout (transition spikes are impulsive).
    Returns (family, confidence, evidence_dict).
    """
    import numpy as np

    amp = dsp.envelope(iq)
    amax = np.max(amp) + 1e-30
    # Active = the signal's "on" samples (gates out burst off-time and deep noise)
    active = amp > 0.3 * amax
    if np.count_nonzero(active) < 32:
        active = amp > np.percentile(amp, 50)

    env_a = amp[active]
    env_cv = float(np.std(env_a) / (np.mean(env_a) + 1e-30))

    flatness = dsp.spectral_flatness(psd_lin)
    par = dsp.papr(iq)

    # Instantaneous frequency on active interior (aligned to iq[1:])
    ifreq = dsp.instantaneous_freq(iq, fs)
    act_mid = active[1:]
    ifr = ifreq[act_mid] if np.any(act_mid) else ifreq
    # Robust frequency deviation: 10–90 percentile span
    fdev = float(np.percentile(ifr, 90) - np.percentile(ifr, 10)) if len(ifr) else 0.0
    fmed = float(np.median(ifr)) if len(ifr) else 0.0

    # Raw-phase clustering (PSK has discrete phase clusters; FSK/FM rotate ~uniformly)
    raw_phase = np.angle(iq[1:][act_mid]) if np.any(act_mid) else np.angle(iq)
    phase_hist, _ = np.histogram(raw_phase, bins=16, range=(-np.pi, np.pi))
    phase_peakiness = float(np.max(phase_hist) / (np.mean(phase_hist) + 1e-30))

    # FSK vs FM: how much time is spent *between* the two frequency levels.
    # FSK dwells at two discrete levels (low mid-band occupancy); a tone-FM
    # sweeps continuously through the middle (high mid-band occupancy).
    mid_frac = 0.0
    if len(ifr) and fdev > 0:
        lvl_lo = np.percentile(ifr, 15)
        lvl_hi = np.percentile(ifr, 85)
        band = lvl_hi - lvl_lo
        if band > 0:
            mid_lo = lvl_lo + 0.3 * band
            mid_hi = lvl_hi - 0.3 * band
            mid_frac = float(np.mean((ifr > mid_lo) & (ifr < mid_hi)))

    bw_rel = (fdev / bw) if bw > 0 else 0.0

    evidence = {
        "env_cv": round(env_cv, 3),
        "spectral_flatness": flatness,
        "papr": par,
        "fdev_hz": round(fdev, 1),
        "fdev_rel_bw": round(bw_rel, 3),
        "phase_peakiness": round(phase_peakiness, 2),
        "mid_frac": round(mid_frac, 3),
        "occupied_bw_hz": round(bw),
        "active_frac": round(float(np.mean(active)), 3),
    }

    # Decision rules (ordered by specificity)
    # OFDM / noise-like: high spectral flatness + high PAPR
    if flatness > 0.5 and par > 8:
        return "OFDM", 0.7, evidence
    # CW: ultra-narrow carrier with near-constant envelope. (Apparent fdev here
    # is dominated by phase noise, not modulation, so a tiny bw is decisive.)
    if bw < 0.005 * fs and env_cv < 0.3:
        return "CW", 0.8, evidence
    # AM: amplitude varies on the active samples while frequency stays put
    if env_cv > 0.3 and fdev < 0.3 * bw:
        return "AM", 0.65, evidence
    # Constant-envelope angle modulations
    if env_cv < 0.4:
        # PSK: discrete phase clusters, carrier frequency steady (small median dev)
        if phase_peakiness > 2.8 and abs(fmed) < 0.25 * bw:
            return "PSK", 0.65, evidence
        # FSK vs FM: significant frequency spread, then split by mid-band dwell
        if fdev > 0.1 * bw:
            if mid_frac < 0.3:
                return "FSK", 0.72, evidence
            return "FM", 0.62, evidence
        # Modest steady frequency offset with no phase clusters → narrowband FM
        if mid_frac >= 0.25:
            return "FM", 0.5, evidence
    # FM fallback: broad continuous frequency excursion
    if fdev > 0.25 * bw and mid_frac >= 0.25:
        return "FM", 0.5, evidence
    return "UNKNOWN", 0.3, evidence


def _characterize(iq, fs: float, center_hz: float) -> dict:
    import numpy as np

    if len(iq) < 64:
        return {"error": "iq_too_short", "samples": int(len(iq))}

    freqs, psd_lin = dsp.welch_psd(iq, fs, nfft=min(8192, len(iq)))
    psd_db = dsp.to_db(psd_lin)

    # Noise-gated PSD for a tight occupied-bandwidth estimate: zero out bins
    # at or near the noise floor (median) so scattered noise residual doesn't
    # inflate the 99%-power span, then subtract the floor from signal bins.
    nf = np.median(psd_lin)
    psd_signal = np.where(psd_lin > 3.0 * nf, psd_lin - nf, 0.0)
    bw = dsp.occupied_bandwidth(freqs, psd_signal, frac=0.99)
    if bw <= 0:
        bw = dsp.occupied_bandwidth(freqs, psd_lin, frac=0.99)

    family, conf, evidence = _classify_modulation(iq, fs, freqs, psd_lin, psd_signal, bw)
    baud = dsp.estimate_baud(iq, fs)
    kind, burst_ms, interval_s, duty = dsp.burst_structure(iq, fs)
    snr = dsp.estimate_snr(psd_db)

    return {
        "center_hz": round(center_hz),
        "bandwidth_hz": round(bw),
        "modulation_family": family,
        "baud_estimate": baud,
        "kind": kind,
        "burst_duration_ms": burst_ms,
        "burst_interval_s": interval_s,
        "duty_cycle": duty,
        "channel_spacing_hz": None,
        "snr": snr,
        "spectral_flatness": evidence["spectral_flatness"],
        "papr": evidence.get("papr"),
        "confidence": round(conf, 2),
        "evidence": evidence,
    }


def main():
    ap = argparse.ArgumentParser(description="Blind DSP feature extraction")
    ap.add_argument("--capture-id", default=None)
    ap.add_argument("--iq-path", default=None)
    ap.add_argument("--sample-rate-hz", type=float, default=None)
    ap.add_argument("--center-hz", type=float, default=0.0)
    ap.add_argument("--retain", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fixture", default=None)
    args = ap.parse_args()

    if args.dry_run:
        if args.fixture:
            print(json.dumps(json.loads(Path(args.fixture).read_text()),
                             ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"error": "dry_run_needs_fixture",
                              "tip": "pass --fixture fixtures/characterize_fixture.json"}))
        return

    iq_path = None
    center_hz = args.center_hz
    meta = None

    if args.capture_id:
        iq_path, fs, center_hz, meta = _resolve_capture(args.capture_id)
    elif args.iq_path:
        if args.sample_rate_hz is None:
            print(json.dumps({"error": "missing_arg",
                              "detail": "--sample-rate-hz required with --iq-path"}))
            sys.exit(1)
        iq_path = Path(args.iq_path)
        fs = args.sample_rate_hz
    else:
        print(json.dumps({"error": "missing_arg",
                          "detail": "provide --capture-id or --iq-path"}))
        sys.exit(1)

    if not iq_path.exists():
        print(json.dumps({"error": "iq_file_missing", "path": str(iq_path)}))
        sys.exit(1)

    iq = dsp.load_iq(str(iq_path))
    fv = _characterize(iq, float(fs), float(center_hz))

    # Auto-delete the IQ (ramdisk hygiene) unless retained
    retain = args.retain or (meta.get("retain") if meta else False)
    if not retain and str(iq_path).startswith(str(SDR_IQ_DIR)):
        try:
            iq_path.unlink()
            sidecar = iq_path.with_suffix(".json")
            sidecar.unlink(missing_ok=True)
        except OSError:
            pass

    print(json.dumps({
        "characterize_id": (args.capture_id or iq_path.stem),
        "source": "capture" if args.capture_id else "iq_path",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iq_deleted": (not retain),
        "feature_vector": fv,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
