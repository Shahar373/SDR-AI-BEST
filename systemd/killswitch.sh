#!/bin/bash
# One-command global kill switch for the SDR agent.
# Stops all agent processes, releases the RF lock, and logs the event.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SDR_DATA_DIR:-$HOME/sdr-data}/logs"
mkdir -p "$LOG_DIR"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) KILLSWITCH ACTIVATED by $(whoami)" | tee -a "$LOG_DIR/audit.jsonl"

# 1. Stop the systemd service
if systemctl is-active --quiet sdr-agent 2>/dev/null; then
    echo "Stopping sdr-agent systemd service..."
    systemctl stop sdr-agent
else
    echo "sdr-agent service not running via systemd."
fi

# 2. Stop OpenClaw gateway directly (in case it was started manually)
if command -v openclaw &>/dev/null; then
    openclaw gateway stop 2>/dev/null || true
fi

# 3. Kill any lingering skill scripts
pkill -f "skills-scripts/" 2>/dev/null || true

# 4. Release RF lock (force, since the owning process is dead)
if [ -f "${SDR_DATA_DIR:-$HOME/sdr-data}/run/rf.lock" ]; then
    python3 /opt/sdr-agent/skills-scripts/rf_lock.py release --force 2>/dev/null || true
fi

# 5. Clean up ramdisk IQ captures
IQ_DIR="${SDR_IQ_DIR:-/dev/shm/sdr-iq}"
if [ -d "$IQ_DIR" ]; then
    echo "Removing IQ captures from ramdisk: $IQ_DIR"
    rm -f "$IQ_DIR"/*.cf32 "$IQ_DIR"/*.cs16 2>/dev/null || true
fi

echo "Kill switch complete. All SDR agent processes stopped."
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) KILLSWITCH COMPLETE" | tee -a "$LOG_DIR/audit.jsonl"
