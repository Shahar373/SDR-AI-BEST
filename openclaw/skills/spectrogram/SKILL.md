---
name: spectrogram
description: Generate a PNG spectrogram (waterfall) artifact for a frequency span. Useful for visual inspection and article illustrations. Saved to the artifacts directory.
user-invocable: true
---

## How to call

```
python3 skills-scripts/spectrogram.py --center-hz 433920000 --span-hz 2000000 --secs 10
```

## Output

```json
{
  "spectrogram_id": "...",
  "path": "/data/sdr/artifacts/spectrogram-....png",
  "center_hz": ..., "span_hz": ..., "duration_secs": ...
}
```
