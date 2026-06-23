"""
Shared DSP utilities for the SDR survey loop.

Pure-numpy/scipy signal math used by sweep, detect, characterize, and
spectrogram. Importing this module does NOT require SoapySDR — it works on
IQ arrays regardless of source (live capture or synthetic fixture).
"""
import numpy as np


def load_iq(path: str) -> np.ndarray:
    """Load an interleaved complex64 .cf32 file into a numpy complex64 array."""
    return np.fromfile(path, dtype=np.complex64)


def save_iq(path: str, iq: np.ndarray) -> None:
    """Write a complex array to a .cf32 file as complex64."""
    iq.astype(np.complex64).tofile(path)


def welch_psd(iq: np.ndarray, fs: float, nfft: int = 4096):
    """
    Averaged power spectral density (Welch-style) with a Blackman window.

    Returns (freqs_hz, psd_linear) where freqs are baseband offsets in Hz
    (fftshifted, so index 0 is -fs/2 and the last is +fs/2).
    """
    nfft = int(min(nfft, len(iq))) or 1
    if nfft < 2:
        return np.array([0.0]), np.array([np.abs(iq).mean() ** 2 if len(iq) else 1e-30])

    win = np.blackman(nfft).astype(np.float32)
    n_frames = max(len(iq) // nfft, 1)
    psd = np.zeros(nfft)
    for i in range(n_frames):
        frame = iq[i * nfft:(i + 1) * nfft]
        if len(frame) < nfft:
            break
        spec = np.fft.fftshift(np.fft.fft(frame * win))
        psd += np.abs(spec) ** 2
    psd /= n_frames
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / fs))
    return freqs, psd


def to_db(psd_linear: np.ndarray) -> np.ndarray:
    """Convert a linear PSD to dB (relative), guarding against log(0)."""
    return 10.0 * np.log10(psd_linear + 1e-30)


def noise_floor(psd_db: np.ndarray, pct: float = 30.0) -> float:
    """Estimate the noise floor as a low percentile of the PSD (dB)."""
    return float(np.percentile(psd_db, pct))


def group_signals(psd_db: np.ndarray, freqs: np.ndarray, center_hz: float,
                  threshold_db: float) -> list[dict]:
    """
    Group contiguous bins above `threshold_db` into discrete signals.

    `freqs` are baseband offsets (Hz) aligned to psd_db; `center_hz` is the
    tuner centre. Returns absolute center_hz, bandwidth_hz, peak_dbfs, occupancy.
    """
    above = psd_db > threshold_db
    nbins = len(psd_db)
    bin_hz = (freqs[1] - freqs[0]) if nbins > 1 else 1.0

    signals = []
    in_sig = False
    start = 0
    for i in range(nbins):
        if above[i] and not in_sig:
            start, in_sig = i, True
        elif (not above[i] or i == nbins - 1) and in_sig:
            end = i if not above[i] else i + 1
            in_sig = False
            width = end - start
            if width < 1:
                continue
            center_bin = (start + end) // 2
            sig_center = center_hz + freqs[min(center_bin, nbins - 1)]
            sig_bw = width * abs(bin_hz)
            peak = float(np.max(psd_db[start:end]))
            occ = float(np.mean(above[start:end]))
            signals.append({
                "center_hz": round(sig_center),
                "bandwidth_hz": round(sig_bw),
                "peak_dbfs": round(peak, 1),
                "occupancy": round(occ, 3),
            })
    return signals


def occupied_bandwidth(freqs: np.ndarray, psd_linear: np.ndarray,
                       frac: float = 0.99) -> float:
    """
    Occupied bandwidth carrying `frac` of total power, centred on the
    power centroid. Returns bandwidth in Hz.
    """
    total = np.sum(psd_linear)
    if total <= 0:
        return 0.0
    # Power-weighted centroid bin
    centroid = int(np.argmax(np.cumsum(psd_linear) >= total / 2))
    target = total * frac
    lo = hi = centroid
    acc = psd_linear[centroid]
    n = len(psd_linear)
    while acc < target and (lo > 0 or hi < n - 1):
        left = psd_linear[lo - 1] if lo > 0 else -1
        right = psd_linear[hi + 1] if hi < n - 1 else -1
        if right >= left:
            hi += 1
            acc += psd_linear[hi]
        else:
            lo -= 1
            acc += psd_linear[lo]
    bin_hz = abs(freqs[1] - freqs[0]) if n > 1 else 1.0
    return float((hi - lo + 1) * bin_hz)


def estimate_snr(psd_db: np.ndarray) -> float:
    """Crude SNR: peak minus noise floor (dB)."""
    return round(float(np.max(psd_db) - noise_floor(psd_db)), 1)


def envelope(iq: np.ndarray) -> np.ndarray:
    """Instantaneous amplitude envelope."""
    return np.abs(iq)


def instantaneous_freq(iq: np.ndarray, fs: float) -> np.ndarray:
    """
    Instantaneous frequency (Hz) via phase difference.
    Length is len(iq)-1. Only meaningful where amplitude is non-trivial.
    """
    phase = np.unwrap(np.angle(iq))
    return np.diff(phase) * fs / (2.0 * np.pi)


def spectral_flatness(psd_linear: np.ndarray) -> float:
    """
    Wiener entropy: geometric mean / arithmetic mean of the PSD.
    ~1.0 = noise-like / OFDM; ~0 = tonal / narrowband carrier.
    """
    p = psd_linear + 1e-30
    gmean = np.exp(np.mean(np.log(p)))
    amean = np.mean(p)
    return round(float(gmean / amean), 4)


def papr(iq: np.ndarray) -> float:
    """Peak-to-average power ratio (linear). High for OFDM/noise-like."""
    amp2 = np.abs(iq) ** 2
    mean = np.mean(amp2)
    if mean <= 0:
        return 0.0
    return round(float(np.max(amp2) / mean), 3)


def burst_structure(iq: np.ndarray, fs: float, on_factor: float = 3.0):
    """
    Detect burst vs continuous from the amplitude envelope.

    Threshold is placed midway between the off-level (10th percentile, ~noise)
    and the on-level (90th percentile, ~signal). A signal with little dynamic
    range between those is continuous.

    Returns (kind, burst_duration_ms, burst_interval_s, duty_cycle).
    kind in {"continuous","burst","intermittent"}.
    """
    env = envelope(iq)
    if len(env) == 0:
        return "unknown", None, None, 0.0

    lo = float(np.percentile(env, 10))
    hi = float(np.percentile(env, 90))
    # Constant-envelope / always-on: on-level not much above off-level
    if hi <= 2.0 * lo + 1e-12:
        return "continuous", None, None, 1.0

    thresh = lo + 0.4 * (hi - lo)
    on = env > thresh
    duty = float(np.mean(on))

    # Find rising/falling edges
    edges = np.diff(on.astype(np.int8))
    rises = np.where(edges == 1)[0]
    falls = np.where(edges == -1)[0]

    if duty > 0.9:
        return "continuous", None, None, duty
    if len(rises) == 0:
        return "continuous" if duty > 0.5 else "intermittent", None, None, duty

    # Average on-duration
    durations = []
    for r in rises:
        later = falls[falls > r]
        if len(later):
            durations.append((later[0] - r) / fs)
    burst_ms = round(float(np.mean(durations)) * 1000, 2) if durations else None

    # Average interval between rises
    interval_s = round(float(np.mean(np.diff(rises)) / fs), 3) if len(rises) > 1 else None
    kind = "burst" if duty < 0.6 else "intermittent"
    return kind, burst_ms, interval_s, round(duty, 3)


def estimate_baud(iq: np.ndarray, fs: float) -> float | None:
    """
    Symbol-rate estimate via the delay-and-multiply spectral-line method on
    the squared magnitude. Returns baud in Hz or None if no clear line.
    """
    if len(iq) < 64:
        return None
    x = np.abs(iq) ** 2
    x = x - np.mean(x)
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), d=1.0 / fs)
    # Ignore DC region
    lo = max(1, int(len(spec) * 0.001))
    if lo >= len(spec):
        return None
    peak_idx = lo + int(np.argmax(spec[lo:]))
    peak_val = spec[peak_idx]
    median = np.median(spec[lo:]) + 1e-30
    if peak_val < 5 * median:  # no significant cyclostationary line
        return None
    return round(float(freqs[peak_idx]), 1)
