---
name: sweep
description: Wideband occupancy sweep across a frequency range. Sweeps in 10 MHz chunks, returns a list of detected signals with center frequency, bandwidth, peak level, and occupancy. Updates the occupancy table in the knowledge base.
user-invocable: true
---

## When to use

- Cron broad sweep — scan the full receivable range
- Before a deep-dive — get an occupancy snapshot of a band
- When the operator asks "what's active on [band]?"

## How to call

```
# Full RSP1B range:
python3 skills-scripts/sweep.py --start-hz 1000 --stop-hz 2000000000 --dwell 1.0

# Specific band:
python3 skills-scripts/sweep.py --start-hz 88000000 --stop-hz 108000000 --dwell 2.0

# Dry-run from fixture (no hardware):
python3 skills-scripts/sweep.py --dry-run --fixture fixtures/sweep_fixture.json
python3 skills-scripts/sweep.py --dry-run
```

## Prerequisites

Hold the rf_lock before calling this in live mode.
Active session required (session_start must have been called).

## Output

```json
{
  "sweep_id": "...",
  "session_id": "...",
  "start_hz": ..., "stop_hz": ...,
  "timestamp": "...",
  "antenna_warnings": ["..."],
  "signals": [
    {"center_hz": ..., "bandwidth_hz": ..., "peak_dbfs": ..., "occupancy": 0.0-1.0}
  ]
}
```

Always surface `antenna_warnings` to the operator — they indicate possible antenna coverage gaps.

## After sweeping

Pass interesting signals (high occupancy, new frequencies, unusual bandwidth) to `detect` for finer resolution, then `characterize`.
