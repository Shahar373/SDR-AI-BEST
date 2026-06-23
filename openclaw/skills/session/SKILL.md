---
name: session
description: Manage work sessions — start, status, end. Every SDR session begins with session_start specifying location, antennas, and goal. Call session_status to check the active session. Call session_end when done.
user-invocable: true
---

## When to use

- The operator says "I'm at location X, antenna Y, today focus on Z" → call `session start`
- You need to know what antenna is connected or what the current goal is → call `session status`
- The operator is done for the day / powering down → call `session end`

## How to call

```
python3 skills-scripts/session.py start --data '{"location": "...", "antennas": [{"name": "...", "min_hz": ..., "max_hz": ..., "notes": "..."}], "goal": "..."}'
python3 skills-scripts/session.py status
python3 skills-scripts/session.py end --summary "..."
```

Antenna `min_hz` and `max_hz` are in Hz (integers or floats). Example for a discone 25–1300 MHz:
```json
{"name": "discone", "min_hz": 25000000, "max_hz": 1300000000, "notes": "roof mount, omnidirectional"}
```

## Output

JSON to stdout. On `start`: `session_id`, `antenna_coverage_advisory`, and the coverage range. On `status`: current session info or `{"status": "no_active_session"}`.

## After starting a session

Always confirm to the operator: "Session started. Antenna coverage: X–Y MHz. Frequencies outside this range will be flagged as possibly antenna-limited rather than signal-absent. Today's goal: Z."
