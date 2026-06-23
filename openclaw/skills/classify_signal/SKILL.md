---
name: classify_signal
description: Modulation/type classification. Heuristic rules in Phase 1; Hailo ML backend in Phase 5. Same JSON contract in both modes. A core mission capability — classify every signal encountered.
user-invocable: false
---

## How to call

```
python3 skills-scripts/classify_signal.py --feature-vector-json '{"modulation_family":"FSK","baud_estimate":4800,...}'
python3 skills-scripts/classify_signal.py --feature-vector-file /tmp/fv.json
python3 skills-scripts/classify_signal.py --backend hailo ...   # Phase 5
```

## Output

```json
{
  "classification": "FSK_NARROWBAND",
  "modulation_family": "FSK",
  "confidence": 0.82,
  "alternatives": [
    {"classification": "GFSK", "confidence": 0.14}
  ],
  "backend": "heuristic"
}
```

## After classifying

Pass feature_vector + classification to `identify`.
