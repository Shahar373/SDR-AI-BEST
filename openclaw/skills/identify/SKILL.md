---
name: identify
description: Cross-reference a signal's characteristics (freq, bandwidth, modulation, baud) against the local signal-reference database. Returns ranked candidate identities or flags the signal as unknown and worth tracking. Also checks the content-decode policy and returns DECODE_ALLOWED for known decodable classes.
user-invocable: false
---

## How to call

```
python3 skills-scripts/identify.py --feature-vector-json '{"center_hz":433920000,"bandwidth_hz":100000,"modulation_family":"FSK","baud_estimate":4800}'
```

## Output

```json
{
  "identity_top": "ISM 433 MHz devices",
  "identity_score": 0.91,
  "status": "identified",
  "candidates": [
    {"name": "ISM 433 MHz devices", "score": 0.91, "category": "ism", "notes": "..."},
    {"name": "PMR446",              "score": 0.21, "category": "ism", "notes": "wrong freq"}
  ],
  "decode_class": "ism",
  "decode_allowed": true,
  "decoder": "decode_ism"
}
```

When `status` is `"unknown"`, recommend tracking: `{"status": "unknown", "tracking_recommendation": "track"}`.

## After identifying

- If `decode_allowed` is true: call the `decoder` skill with the IQ or capture reference.
- Always call `catalog_upsert` with the full observation.
