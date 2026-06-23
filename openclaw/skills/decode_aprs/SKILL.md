---
name: decode_aprs
description: Decode APRS position and telemetry reports on 144.800 MHz (Israel) using FM demodulation and direwolf/multimon-ng. All text through sanitize_rf_text.
user-invocable: false
---

## How to call

```
python3 skills-scripts/decoders/decode_aprs.py --duration-secs 120
python3 skills-scripts/decoders/decode_aprs.py --dry-run --fixture fixtures/aprs_fixture.json
```
