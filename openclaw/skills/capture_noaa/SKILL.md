---
name: capture_noaa
description: Receive and decode a NOAA weather satellite APT image pass using satdump. Must be scheduled for a satellite pass (use a pass predictor). Saves PNG image artifact.
user-invocable: true
---

## How to call

```
python3 skills-scripts/decoders/capture_noaa.py --freq-hz 137912500 --duration-secs 900
python3 skills-scripts/decoders/capture_noaa.py --dry-run --fixture fixtures/noaa_fixture.json
```
