---
name: catalog_query
description: Query the spectrum knowledge base. Use this to answer operator questions, build digests, and check the catalog before reporting anomalies.
user-invocable: true
---

## How to call

```
# All signals in a frequency range:
python3 skills-scripts/catalog.py query --min-hz 430000000 --max-hz 440000000

# Signals by status:
python3 skills-scripts/catalog.py query --status unknown

# Recent activity (last N hours):
python3 skills-scripts/catalog.py query --last-hours 24

# Specific signal:
python3 skills-scripts/catalog.py query --emitter-key "433920000_FSK"

# Full time window for digest:
python3 skills-scripts/catalog.py query --from "2026-06-23T00:00:00Z" --to "2026-06-23T23:59:59Z"
```
