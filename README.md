# SDR AI Spectrum Analysis Agent

Autonomous passive spectrum-analysis agent running on a Raspberry Pi 5 with an SDRplay RSP1B, orchestrated by [OpenClaw](https://github.com/openclaw/openclaw) with Claude Opus as the model.

The agent roams the full receivable spectrum (1 kHz – 2 GHz), characterizes every signal it finds blind (no prior knowledge required), builds a persistent spectrum knowledge base, and narrates findings via Telegram and periodic Hebrew RTL spectrum-intelligence articles.

**Passive RX only. Never transmits.**

---

## Architecture

```
[ RSP1B ] → SoapySDR/SoapySDRPlay3 → Device Arbiter (rf_lock)
                                             │
                  ┌──────────────────────────┴──────────────────────────────┐
                  ▼  Python CLI skills (JSON stdout + artifact paths)        ▼
   sweep / detect / capture_iq / characterize / classify_signal / identify
   decode_adsb / decode_ais / decode_acars / decode_aprs / decode_ism / capture_noaa
                  │
                  ▼  all RF text → sanitize_rf_text → [UNTRUSTED RF DATA]
   ┌── Session Store ──┐   ┌──── Spectrum Knowledge Base (SQLite) ────────┐
   │ location/antennas │   │ occupancy · signal catalog · feature vectors │
   │ goal · methods    │──▶│ observations · artifacts                     │
   └───────────────────┘   └──────────────────────────────────────────────┘
                  │
                  ▼
   [ OpenClaw + Claude Opus 4.8 ]
     cron sweeps · anomaly heartbeat · revisit strategy · curiosity budget
                  │
                  ▼
   Telegram pings · daily digest · Hebrew RTL articles (council-reviewed)
```

---

## Quick Start (fresh Pi 5)

```bash
git clone https://github.com/shahar373/sdr-ai-best.git
cd sdr-ai-best

# Download SDRplay API from https://www.sdrplay.com/api/
# Place SDRplay_RSP_API-Linux-*.run in provision/

sudo bash provision/install.sh
sudo -u sdruser nano /opt/sdr-agent/.env   # fill in API keys
sudo systemctl start sdr-agent
sudo journalctl -u sdr-agent -f
```

---

## Repository Structure

```
provision/install.sh          Idempotent Pi 5 provisioning script
openclaw/
  openclaw.config.json        OpenClaw gateway config
  agents/sdr-agent/
    SOUL.md                   Agent persona and system-prompt rules
    agent.config.json         Model, failover, tool allow-list
  skills/*/SKILL.md           Skill definitions (22 skills)
  cron/jobs.json              Scheduled tasks (sweep, heartbeat, digest, article)
skills-scripts/               Python CLI backends for all skills
  lib/                        Shared utilities (env, db, session_store)
  decoders/                   Opportunistic decoder wrappers
db/
  schema.sql                  Knowledge base schema
  migrations/                 Versioned migrations
  signal_reference_schema.sql Signal reference DB schema
  populate_signal_reference.py Populate with ~34 known signal types (Israel-area)
fixtures/                     Replay fixtures for development without live RF
policy/content_decode.json    Operator-owned decode policy (all classes enabled)
systemd/
  sdr-agent.service           systemd unit
  killswitch.sh               One-command global stop
.env.example                  Environment variable template
```

---

## Skills

### Session & context
| Skill | Description |
|---|---|
| `session` | Start/status/end a work session. Pins location, antennas, and goal. |

### Core survey chain (the spine)
| Skill | Description |
|---|---|
| `rf_lock` | Exclusive device arbiter for the single tuner |
| `sweep` | Wideband occupancy sweep, 10 MHz chunks |
| `detect` | Discrete signal finder in a span |
| `capture_iq` | Short IQ capture to ramdisk (duration-capped, auto-deleted) |
| `spectrogram` | PNG waterfall artifact |
| `characterize` | Blind DSP feature extraction (modulation, baud, burst structure) |
| `classify_signal` | Heuristic classifier (Phase 5: Hailo ML backend, same contract) |
| `identify` | Cross-reference features vs signal-reference DB |

### Opportunistic decoders (Phase 2+)
| Skill | Decoder | Signal |
|---|---|---|
| `decode_adsb` | dump1090-fa | ADS-B 1090 MHz |
| `decode_ais` | AIS-catcher | AIS 161.975/162.025 MHz |
| `decode_acars` | acarsdec | ACARS aviation data-link |
| `decode_aprs` | direwolf | APRS 144.8 MHz |
| `decode_ism` | rtl_433 | 433/868 MHz ISM devices |
| `capture_noaa` | satdump | NOAA APT weather satellite |

### Knowledge base & output
| Skill | Description |
|---|---|
| `catalog_upsert` | Write observation to knowledge base |
| `catalog_query` | Query knowledge base (band, status, time window) |
| `signal_track` | Longitudinal emitter tracking across sessions |
| `write_article` | Hebrew RTL spectrum-intelligence article draft |
| `council_review` | 4-persona adversarial review (mandatory before publishing) |
| `sanitize_rf_text` | Prompt-injection sanitizer for all RF-derived text |

---

## Skill CLI test commands

```bash
cd /opt/sdr-agent

# Session dry-run
python3 skills-scripts/session.py start --dry-run \
  --data '{"location":"home","antennas":[{"name":"discone","min_hz":25000000,"max_hz":1300000000}],"goal":"test"}'

# Sweep dry-run (no hardware)
python3 skills-scripts/sweep.py --dry-run
python3 skills-scripts/sweep.py --dry-run --fixture fixtures/sweep_fixture.json

# RF lock test (open two terminals)
python3 skills-scripts/rf_lock.py status
python3 skills-scripts/rf_lock.py acquire --holder test-1
# In second terminal: python3 skills-scripts/rf_lock.py acquire --holder test-2 --timeout 5  → should timeout
python3 skills-scripts/rf_lock.py release

# Characterize dry-run
python3 skills-scripts/characterize.py --dry-run --fixture fixtures/characterize_fixture.json

# Identify test
python3 skills-scripts/identify.py \
  --feature-vector-json '{"center_hz":433920000,"bandwidth_hz":100000,"modulation_family":"FSK","baud_estimate":4800}'

# Populate signal reference DB
python3 db/populate_signal_reference.py
```

---

## Security

- OpenClaw sandbox (Docker) with non-privileged `sdruser`
- Network egress allowlist: `api.anthropic.com` + `api.telegram.org` only
- All RF-derived text passes `sanitize_rf_text.py` and is labeled `[UNTRUSTED RF DATA]`
- Action allowlist enforced in `agent.config.json` — no exec outside the 22 allowed skills
- `security.installPolicy: strict` — no third-party skills
- Full audit log at `$SDR_DATA_DIR/logs/audit.jsonl`
- Kill switch: `sudo sdr-agent-stop`

---

## Phased build

| Phase | Goal | Status |
|---|---|---|
| 0 — Foundation | Provisioning, OpenClaw config, session/lock, DB, fixtures, systemd | ✅ In progress |
| 1 — Roaming MVP | sweep→detect→characterize→classify→identify→catalog loop on real RF | 🔜 |
| 2 — Opportunistic decode | ADS-B, AIS, ACARS, APRS, ISM, NOAA one at a time | 🔜 |
| 3 — Widen & deepen | Full range, revisit strategy, emitter tracking, anomaly detection | 🔜 |
| 4 — Narration | Hebrew articles + council review | 🔜 |
| 5 — ML characterization | Hailo-accelerated AMC / RF fingerprinting | 🔜 |

---

## Kill switch

```bash
sudo sdr-agent-stop
```

Stops all agent processes, releases the RF lock, cleans the IQ ramdisk, and logs the event.
