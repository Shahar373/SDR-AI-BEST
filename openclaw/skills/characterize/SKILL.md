---
name: characterize
description: Blind DSP feature extraction from an IQ capture or reference. Estimates modulation family, bandwidth, symbol/baud rate, burst structure, channel spacing — without being told what the signal is. Returns a feature vector JSON.
user-invocable: false
---

## How to call

```
python3 skills-scripts/characterize.py --capture-id CAPTURE_ID
python3 skills-scripts/characterize.py --iq-path /dev/shm/sdr-iq/capture-X.cf32 --sample-rate-hz 200000
python3 skills-scripts/characterize.py --dry-run --fixture fixtures/characterize_fixture.json
```

## Output

```json
{
  "characterize_id": "...",
  "feature_vector": {
    "center_hz": ...,
    "bandwidth_hz": ...,
    "modulation_family": "AM|FM|FSK|PSK|OFDM|CW|UNKNOWN",
    "baud_estimate": ...,
    "kind": "continuous|burst|intermittent",
    "burst_duration_ms": ...,
    "burst_interval_s": ...,
    "channel_spacing_hz": ...,
    "snr": ...,
    "confidence": 0.0-1.0
  }
}
```

## After characterizing

Pass the feature_vector to `classify_signal` then `identify`.
The IQ file is deleted after this call (unless captured with --retain).
