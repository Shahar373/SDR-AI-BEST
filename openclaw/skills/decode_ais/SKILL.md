---
name: decode_ais
description: Decode AIS vessel tracking on 161.975 / 162.025 MHz using AIS-catcher with native SDRplay support. Only when identify returns decode_class=ais. All text through sanitize_rf_text.
user-invocable: false
---

## How to call

```
python3 skills-scripts/decoders/decode_ais.py --duration-secs 120
python3 skills-scripts/decoders/decode_ais.py --dry-run --fixture fixtures/ais_fixture.json
```
