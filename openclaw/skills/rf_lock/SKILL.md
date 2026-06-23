---
name: rf_lock
description: Acquire and release exclusive access to the single RSP1B tuner. Every skill that touches the radio must acquire the lock first. Never attempt radio operations without holding the lock.
user-invocable: false
---

## When to use

Call `rf_lock acquire` before every sweep, detect, capture_iq, spectrogram, or decode operation.
Call `rf_lock release` when the radio operation is complete (or if the operation fails).

## How to call

```
python3 skills-scripts/rf_lock.py acquire --timeout 30 --holder SKILL_NAME
python3 skills-scripts/rf_lock.py release
python3 skills-scripts/rf_lock.py status
```

## Output

JSON: `{"status": "acquired", "pid": ..., "holder": "...", "acquired_at": "..."}` on success.
`{"error": "lock_timeout", ...}` if the lock cannot be acquired within timeout seconds.

## Important

If `acquire` times out, do NOT proceed with the radio operation. Report to the operator that the tuner is busy and retry in the next cycle. Use `rf_lock status` to see who holds the lock.
