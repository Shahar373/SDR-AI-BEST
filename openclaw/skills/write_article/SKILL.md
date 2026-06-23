---
name: write_article
description: Draft a Hebrew RTL spectrum-intelligence article from catalog data. Always follows §11 style rules — technical precision, no sensationalism, no operational detail that aids misuse, DEF CON / JawnCon framing. Article is NOT published until council_review passes and operator approves.
user-invocable: true
---

## How to call

```
python3 skills-scripts/write_article.py --topic "weekly_summary" --time-window "7d"
python3 skills-scripts/write_article.py --topic "tracked_unknown_emitter" --emitter-key "433920000_FSK"
```

## Topics

- `weekly_summary` — full week RF landscape: occupancy, identified vs unknown, anomalies
- `tracked_unknown_emitter` — deep-dive on a specific tracked emitter
- `band_survey` — survey of a specific band (pass --band "433 MHz ISM")
- `anomaly_report` — focused report on an anomalous finding

## After writing

**Always** call `council_review` before presenting the draft to the operator.
