---
name: decode_acars
description: Decode ACARS aviation data-link messages using acarsdec. Monitors standard ACARS frequencies (129.125, 131.725, 136.9 MHz). All text through sanitize_rf_text.
user-invocable: false
---

## How to call

```
python3 skills-scripts/decoders/decode_acars.py --duration-secs 300
python3 skills-scripts/decoders/decode_acars.py --dry-run --fixture fixtures/acars_fixture.json
```
