---
name: detect
description: Find discrete signals in a frequency span — carriers, bursts, channelized activity. More precise than sweep; use after sweep identifies an interesting region.
user-invocable: true
---

## How to call

```
python3 skills-scripts/detect.py --center-hz 433920000 --span-hz 2000000 --secs 5
python3 skills-scripts/detect.py --dry-run --fixture fixtures/detect_fixture.json
```

## Prerequisites

Hold rf_lock. Active session.

## Output

```json
{
  "detect_id": "...",
  "session_id": "...",
  "center_hz": ..., "span_hz": ...,
  "timestamp": "...",
  "signals": [
    {"center_hz": ..., "bandwidth_hz": ..., "kind": "continuous|burst", "snr": ...}
  ]
}
```

## After detecting

For each signal of interest, call `capture_iq` then `characterize`.
