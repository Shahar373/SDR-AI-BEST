---
name: catalog_upsert
description: Write or update a signal observation to the spectrum knowledge base. Call this after every complete characterize→classify→identify chain. This is how the agent maintains its world-model.
user-invocable: false
---

## How to call

```
python3 skills-scripts/catalog.py upsert --observation-json '{"center_hz":433920000,...}'
```

The observation JSON should include: center_hz, bandwidth_hz, modulation_family, baud_estimate, kind, identity_top, identity_score, identity_candidates, status, snr, feature_vector, decoder_output (if any), artifact_path (if any).
