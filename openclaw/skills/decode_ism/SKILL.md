---
name: decode_ism
description: Decode ISM-band devices (433/868 MHz) using rtl_433 with SoapySDR input. Covers weather stations, door sensors, remote controls, power meters. All text through sanitize_rf_text.
user-invocable: false
---

## How to call

```
python3 skills-scripts/decoders/decode_ism.py --center-hz 433920000 --duration-secs 60
python3 skills-scripts/decoders/decode_ism.py --dry-run --fixture fixtures/ism_fixture.json
```
