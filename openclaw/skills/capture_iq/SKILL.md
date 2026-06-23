---
name: capture_iq
description: Capture a short IQ recording to ramdisk for characterization. Hard caps enforced by env vars (SDR_IQ_MAX_SECS, SDR_IQ_MAX_MB). IQ is deleted automatically after characterize uses it unless --retain is passed.
user-invocable: false
---

## How to call

```
python3 skills-scripts/capture_iq.py --center-hz 433920000 --span-hz 200000 --secs 5
```

## Prerequisites

Hold rf_lock. Active session. Do NOT capture more than SDR_MAX_IQ_CAPTURES_PER_CYCLE (default 5) per sweep cycle — curiosity budget.

## Output

```json
{
  "capture_id": "...",
  "path": "/dev/shm/sdr-iq/capture-....cf32",
  "center_hz": ..., "sample_rate_hz": ..., "duration_secs": ...,
  "size_mb": ...,
  "auto_delete_after": "characterize"
}
```

## After capturing

Pass `capture_id` or the `path` to `characterize`. The file is deleted once characterize reads it.
