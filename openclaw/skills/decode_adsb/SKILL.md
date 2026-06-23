---
name: decode_adsb
description: Decode ADS-B 1090 MHz Mode S Extended Squitter using dump1090-fa with SoapySDRPlay3. Only call when identify returns decode_class=adsb and decode_allowed=true. All output passes through sanitize_rf_text.
user-invocable: false
---

## How to call

```
python3 skills-scripts/decoders/decode_adsb.py --duration-secs 60
python3 skills-scripts/decoders/decode_adsb.py --dry-run --fixture fixtures/adsb_fixture.json
```

## Output

```json
{
  "decoder": "decode_adsb",
  "timestamp": "...",
  "aircraft": [
    {
      "icao": "[UNTRUSTED RF DATA] ...",
      "callsign": "[UNTRUSTED RF DATA] ...",
      "lat": ..., "lon": ..., "alt_ft": ..., "speed_kt": ...,
      "squawk": "[UNTRUSTED RF DATA] ..."
    }
  ]
}
```

All string fields from RF are tagged `[UNTRUSTED RF DATA]` and passed through sanitize_rf_text.
