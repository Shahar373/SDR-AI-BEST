"""
SoapySDR streaming helpers — lazy import + robust read loop.

Centralises device open/close and a read loop that tolerates the transient
TIMEOUT/OVERFLOW returns the RSP1B emits right after activateStream and at
high sample rates. Without this, a single readStream (or breaking on the
first non-positive return) yields short or empty captures on real hardware.
"""
import json
import sys
import time


def _soapy():
    try:
        import SoapySDR
        import numpy as np
        return SoapySDR, np
    except ImportError as exc:
        print(json.dumps({
            "error": "missing_dependency",
            "detail": str(exc),
            "tip": "Run provision/install.sh to install SoapySDR + SoapySDRPlay3",
        }))
        sys.exit(1)


def open_rx(center_hz: float, fs: float, antenna: str | None = None,
            agc: bool = True, driver: str = "SoapySDRPlay3"):
    """Open an RX stream on the RSP1B and return (sdr, stream)."""
    SoapySDR, _ = _soapy()
    sdr = SoapySDR.Device({"driver": driver})
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, float(fs))
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, float(center_hz))
    if antenna:
        sdr.setAntenna(SoapySDR.SOAPY_SDR_RX, 0, antenna)
    sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, bool(agc))
    stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(stream)
    return sdr, stream


def retune(sdr, center_hz: float):
    SoapySDR, _ = _soapy()
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, float(center_hz))


def read_samples(sdr, stream, n_samples: int, fs: float,
                 max_wait_s: float | None = None):
    """
    Read up to n_samples, tolerating transient TIMEOUT/OVERFLOW until a
    wall-clock deadline (default 2x the expected capture time, min 5s).
    Returns a complex64 numpy array of the samples actually collected.
    """
    SoapySDR, np = _soapy()
    buf = np.zeros(n_samples, dtype=np.complex64)
    got = 0
    expected = (n_samples / fs) if fs else 1.0
    deadline = time.monotonic() + (max_wait_s if max_wait_s else max(2.0 * expected, 5.0))

    while got < n_samples:
        if time.monotonic() > deadline:
            break
        chunk = np.zeros(min(1 << 16, n_samples - got), dtype=np.complex64)
        sr = sdr.readStream(stream, [chunk], len(chunk), timeoutUs=200_000)
        if sr.ret > 0:
            buf[got:got + sr.ret] = chunk[:sr.ret]
            got += sr.ret
        elif sr.ret in (SoapySDR.SOAPY_SDR_TIMEOUT, SoapySDR.SOAPY_SDR_OVERFLOW):
            continue  # transient — keep trying until the deadline
        else:
            break  # fatal stream error (STREAM_ERROR / CORRUPTION / etc.)

    return buf[:got]


def close(sdr, stream):
    try:
        sdr.deactivateStream(stream)
        sdr.closeStream(stream)
    except Exception:
        pass
