#!/bin/bash
# SDR Spectrum Analysis Agent — fresh Raspberry Pi 5 provisioning script
#
# Idempotent: safe to run multiple times. Each step checks before acting.
#
# Prerequisites:
#   - Raspberry Pi 5 running Raspberry Pi OS (64-bit Bookworm)
#   - Internet access
#   - RSP1B connected via USB (can be done before or after)
#   - SDRplay API .run installer placed in the same directory as this script
#     (download from https://www.sdrplay.com/api/ — requires accepting the license)
#
# Usage:
#   sudo bash provision/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/sdr-agent-provision.log"
INSTALL_PREFIX="/opt/sdr-agent"
SDRUSER="sdruser"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[!]${NC} $*" | tee -a "$LOG_FILE"; }
die()  { echo -e "${RED}[✗]${NC} $*" | tee -a "$LOG_FILE"; exit 1; }

require_root() {
    [[ $EUID -eq 0 ]] || die "Run this script as root: sudo bash provision/install.sh"
}

# ── 0. Preflight ─────────────────────────────────────────────────────────
require_root
log "SDR Agent provisioning started. Log: $LOG_FILE"
log "Detected OS: $(uname -a)"

# ── 1. System packages ────────────────────────────────────────────────────
log "Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    build-essential cmake git pkg-config \
    libusb-1.0-0-dev libudev-dev \
    python3 python3-pip python3-venv python3-dev \
    libfftw3-dev libsoapysdr-dev soapysdr-tools \
    libboost-all-dev \
    rtl-sdr \
    sox \
    curl wget jq \
    sqlite3 \
    docker.io \
    2>&1 | tee -a "$LOG_FILE"

# ── 2. SDRplay API 3.x ────────────────────────────────────────────────────
log "Checking SDRplay API..."
if ldconfig -p | grep -q libsdrplay_api; then
    warn "SDRplay API already installed — skipping."
else
    SDRPLAY_INSTALLER=$(ls "$SCRIPT_DIR"/SDRplay_RSP_API-Linux-*.run 2>/dev/null | head -1)
    if [[ -z "$SDRPLAY_INSTALLER" ]]; then
        warn "SDRplay API installer not found in provision/"
        warn "Download SDRplay_RSP_API-Linux-*.run from https://www.sdrplay.com/api/"
        warn "Place it in provision/ then re-run this script."
        warn "Continuing without SDRplay API — live RF will not work until it is installed."
    else
        log "Installing SDRplay API from: $SDRPLAY_INSTALLER"
        chmod +x "$SDRPLAY_INSTALLER"
        "$SDRPLAY_INSTALLER" -- --noexec --keep --target /tmp/sdrplay_api_install
        /tmp/sdrplay_api_install/install_lib.sh 2>&1 | tee -a "$LOG_FILE"
        ldconfig
        log "SDRplay API installed."
    fi
fi

# ── 3. SoapySDRPlay3 plugin ───────────────────────────────────────────────
log "Checking SoapySDRPlay3..."
if python3 -c "import SoapySDR; d=SoapySDR.Device.enumerate({'driver':'SoapySDRPlay3'})" &>/dev/null 2>&1; then
    warn "SoapySDRPlay3 already present — skipping build."
else
    log "Building SoapySDRPlay3 from source..."
    TMPDIR=$(mktemp -d)
    git clone --depth 1 https://github.com/SDRplay/SoapySDRPlay3.git "$TMPDIR/SoapySDRPlay3" \
        2>&1 | tee -a "$LOG_FILE"
    cmake -S "$TMPDIR/SoapySDRPlay3" -B "$TMPDIR/build" \
        -DCMAKE_BUILD_TYPE=Release 2>&1 | tee -a "$LOG_FILE"
    cmake --build "$TMPDIR/build" -j"$(nproc)" 2>&1 | tee -a "$LOG_FILE"
    cmake --install "$TMPDIR/build" 2>&1 | tee -a "$LOG_FILE"
    ldconfig
    rm -rf "$TMPDIR"
    log "SoapySDRPlay3 installed."
fi

# ── 4. External decoder tools ─────────────────────────────────────────────
install_if_missing() {
    local cmd=$1 pkg=$2
    if command -v "$cmd" &>/dev/null; then
        warn "$cmd already installed — skipping."
    else
        log "Installing $pkg..."
        apt-get install -y --no-install-recommends "$pkg" 2>&1 | tee -a "$LOG_FILE"
    fi
}

log "Installing decoder tools..."
# dump1090-fa (ADS-B)
if ! command -v dump1090-fa &>/dev/null; then
    log "Installing dump1090-fa..."
    curl -s https://repo.flyingpigs.io/packages/dump1090/dump1090-fa-latest-arm64.deb \
        -o /tmp/dump1090-fa.deb 2>&1 | tee -a "$LOG_FILE" || \
    apt-get install -y dump1090-fa 2>&1 | tee -a "$LOG_FILE" || \
    warn "dump1090-fa install failed — ADS-B decode unavailable until installed manually."
else
    warn "dump1090-fa already installed."
fi

# AIS-catcher
if ! command -v AIS-catcher &>/dev/null; then
    log "Building AIS-catcher..."
    TMPDIR=$(mktemp -d)
    git clone --depth 1 https://github.com/jvde-github/AIS-catcher.git "$TMPDIR/AIS-catcher" \
        2>&1 | tee -a "$LOG_FILE"
    cmake -S "$TMPDIR/AIS-catcher" -B "$TMPDIR/build-ais" -DCMAKE_BUILD_TYPE=Release \
        2>&1 | tee -a "$LOG_FILE"
    cmake --build "$TMPDIR/build-ais" -j"$(nproc)" 2>&1 | tee -a "$LOG_FILE"
    cmake --install "$TMPDIR/build-ais" 2>&1 | tee -a "$LOG_FILE"
    rm -rf "$TMPDIR"
    log "AIS-catcher installed."
else
    warn "AIS-catcher already installed."
fi

install_if_missing direwolf direwolf   # APRS
install_if_missing multimon-ng multimon-ng
install_if_missing acarsdec acarsdec   # ACARS (may need PPA or build from source)

# rtl_433
if ! command -v rtl_433 &>/dev/null; then
    log "Installing rtl_433..."
    apt-get install -y rtl-433 2>&1 | tee -a "$LOG_FILE" || {
        warn "rtl_433 not in apt — building from source..."
        TMPDIR=$(mktemp -d)
        git clone --depth 1 https://github.com/merbanan/rtl_433.git "$TMPDIR/rtl_433" \
            2>&1 | tee -a "$LOG_FILE"
        cmake -S "$TMPDIR/rtl_433" -B "$TMPDIR/build-rtl433" -DCMAKE_BUILD_TYPE=Release \
            2>&1 | tee -a "$LOG_FILE"
        cmake --build "$TMPDIR/build-rtl433" -j"$(nproc)" 2>&1 | tee -a "$LOG_FILE"
        cmake --install "$TMPDIR/build-rtl433" 2>&1 | tee -a "$LOG_FILE"
        rm -rf "$TMPDIR"
    }
else
    warn "rtl_433 already installed."
fi

# satdump (NOAA APT)
if ! command -v satdump &>/dev/null; then
    log "Building satdump..."
    apt-get install -y --no-install-recommends \
        libpng-dev libjpeg-dev zlib1g-dev libvolk2-dev \
        libogg-dev libvorbis-dev 2>&1 | tee -a "$LOG_FILE"
    TMPDIR=$(mktemp -d)
    git clone --depth 1 https://github.com/SatDump/SatDump.git "$TMPDIR/satdump" \
        2>&1 | tee -a "$LOG_FILE"
    cmake -S "$TMPDIR/satdump" -B "$TMPDIR/build-satdump" \
        -DCMAKE_BUILD_TYPE=Release -DBUILD_GUI=OFF 2>&1 | tee -a "$LOG_FILE"
    cmake --build "$TMPDIR/build-satdump" -j"$(nproc)" 2>&1 | tee -a "$LOG_FILE"
    cmake --install "$TMPDIR/build-satdump" 2>&1 | tee -a "$LOG_FILE"
    rm -rf "$TMPDIR"
    log "satdump installed."
else
    warn "satdump already installed."
fi

# ── 5. Python virtual environment ─────────────────────────────────────────
log "Setting up Python virtual environment..."
VENV="$INSTALL_PREFIX/venv"
if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip wheel 2>&1 | tee -a "$LOG_FILE"
"$VENV/bin/pip" install \
    numpy scipy matplotlib Pillow \
    2>&1 | tee -a "$LOG_FILE"

# SoapySDR Python bindings (usually installed system-wide with the C++ library)
"$VENV/bin/pip" install --extra-index-url https://pypi.org/simple SoapySDR 2>/dev/null || \
    warn "SoapySDR Python via pip failed — using system bindings (add to PYTHONPATH if needed)"

# ── 6. OpenClaw ────────────────────────────────────────────────────────────
log "Installing OpenClaw..."
OPENCLAW_VERSION="0.4.2"   # pin; check https://github.com/openclaw/openclaw/releases
if command -v openclaw &>/dev/null && openclaw --version 2>/dev/null | grep -q "$OPENCLAW_VERSION"; then
    warn "OpenClaw $OPENCLAW_VERSION already installed."
else
    # Install via the official install script
    curl -fsSL https://get.openclaw.ai | bash -s -- --version "$OPENCLAW_VERSION" \
        2>&1 | tee -a "$LOG_FILE" || \
    die "OpenClaw installation failed. Check $LOG_FILE for details."
fi

# ── 7. Create sdruser and set permissions ────────────────────────────────
log "Setting up sdruser..."
if ! id "$SDRUSER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$INSTALL_PREFIX" -G plugdev,dialout,docker "$SDRUSER"
    log "Created user $SDRUSER"
else
    warn "User $SDRUSER already exists."
fi

# ── 8. Detect and configure storage ──────────────────────────────────────
log "Detecting storage..."
if mountpoint -q /mnt/sdr-ssd 2>/dev/null; then
    SDR_DATA_DIR="/mnt/sdr-ssd/sdr-agent"
    log "SSD detected at /mnt/sdr-ssd → using $SDR_DATA_DIR"
else
    SDR_DATA_DIR="/home/$SDRUSER/sdr-data"
    warn "No SSD at /mnt/sdr-ssd. Using $SDR_DATA_DIR (SD card — not ideal for production)."
    warn "Mount an SSD at /mnt/sdr-ssd and re-run to migrate."
fi

# ── 9. Install project files ───────────────────────────────────────────────
log "Installing project to $INSTALL_PREFIX..."
mkdir -p "$INSTALL_PREFIX"
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    "$REPO_DIR/" "$INSTALL_PREFIX/" 2>&1 | tee -a "$LOG_FILE"
chown -R "$SDRUSER:$SDRUSER" "$INSTALL_PREFIX"

# ── 10. Create data directories ───────────────────────────────────────────
log "Creating data directories..."
for d in "$SDR_DATA_DIR" "$SDR_DATA_DIR/session" "$SDR_DATA_DIR/run" \
          "$SDR_DATA_DIR/artifacts" "$SDR_DATA_DIR/articles" "$SDR_DATA_DIR/logs"; do
    mkdir -p "$d"
    chown "$SDRUSER:$SDRUSER" "$d"
done

# Ramdisk for IQ: /dev/shm is already tmpfs on Pi OS
IQ_DIR="/dev/shm/sdr-iq"
mkdir -p "$IQ_DIR"
chown "$SDRUSER:$SDRUSER" "$IQ_DIR"

# ── 11. Initialise databases ─────────────────────────────────────────────
log "Initialising knowledge base..."
sudo -u "$SDRUSER" sqlite3 "$SDR_DATA_DIR/sdr-knowledge.sqlite" \
    < "$INSTALL_PREFIX/db/schema.sql" 2>&1 | tee -a "$LOG_FILE"

log "Populating signal reference database..."
sudo -u "$SDRUSER" python3 "$INSTALL_PREFIX/db/populate_signal_reference.py" \
    --db "$INSTALL_PREFIX/db/signal_reference.db" 2>&1 | tee -a "$LOG_FILE"

# ── 12. Configure .env ────────────────────────────────────────────────────
ENV_FILE="$INSTALL_PREFIX/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$INSTALL_PREFIX/.env.example" "$ENV_FILE"
    sed -i "s|SDR_DATA_DIR=.*|SDR_DATA_DIR=$SDR_DATA_DIR|" "$ENV_FILE"
    chown "$SDRUSER:$SDRUSER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    warn "Created .env from template. Fill in ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID:"
    warn "  sudo -u $SDRUSER nano $ENV_FILE"
else
    warn ".env already exists — not overwriting."
fi

# ── 13. Systemd service ───────────────────────────────────────────────────
log "Installing systemd service..."
cp "$INSTALL_PREFIX/systemd/sdr-agent.service" /etc/systemd/system/sdr-agent.service
sed -i "s|/opt/sdr-agent|$INSTALL_PREFIX|g" /etc/systemd/system/sdr-agent.service
systemctl daemon-reload
systemctl enable sdr-agent
log "Service installed and enabled (not started yet — fill in .env first)."

# ── 14. Kill switch ───────────────────────────────────────────────────────
log "Installing kill switch..."
cp "$INSTALL_PREFIX/systemd/killswitch.sh" /usr/local/bin/sdr-agent-stop
chmod +x /usr/local/bin/sdr-agent-stop
sed -i "s|/opt/sdr-agent|$INSTALL_PREFIX|g" /usr/local/bin/sdr-agent-stop
log "Kill switch installed: run 'sudo sdr-agent-stop' to stop everything immediately."

# ── 15. USB udev rules for RSP1B ─────────────────────────────────────────
log "Installing udev rules for RSP1B..."
cat > /etc/udev/rules.d/66-sdrplay.rules << 'EOF'
# SDRplay RSP devices
SUBSYSTEM=="usb", ATTR{idVendor}=="1df7", MODE="0664", GROUP="plugdev"
EOF
udevadm control --reload-rules
udevadm trigger
log "udev rules installed. Unplug and replug the RSP1B if already connected."

# ── 16. Verification ──────────────────────────────────────────────────────
log "Running smoke tests..."
PYTHON="$INSTALL_PREFIX/venv/bin/python3"
[[ -f "$PYTHON" ]] || PYTHON=python3

# Test session dry-run
SESSION_TEST=$(sudo -u "$SDRUSER" "$PYTHON" "$INSTALL_PREFIX/skills-scripts/session.py" \
    start --dry-run \
    --data '{"location":"provision-test","antennas":[{"name":"test","min_hz":88000000,"max_hz":108000000}],"goal":"smoke test"}' \
    2>&1)
if echo "$SESSION_TEST" | grep -q '"status": "dry_run_ok"'; then
    log "  ✓ session.py dry-run OK"
else
    warn "  ✗ session.py dry-run failed: $SESSION_TEST"
fi

# Test sweep dry-run
SWEEP_TEST=$(sudo -u "$SDRUSER" "$PYTHON" "$INSTALL_PREFIX/skills-scripts/sweep.py" \
    --dry-run 2>&1)
if echo "$SWEEP_TEST" | grep -q '"signals"'; then
    log "  ✓ sweep.py dry-run OK"
else
    warn "  ✗ sweep.py dry-run failed: $SWEEP_TEST"
fi

# Test SoapySDR (hardware optional — skip if not connected)
if sudo -u "$SDRUSER" SoapySDRUtil --find 2>&1 | grep -q "SDRplay"; then
    log "  ✓ RSP1B detected via SoapySDR"
else
    warn "  ⚠ RSP1B not detected (may not be connected yet — that's OK)"
fi

# ── Done ──────────────────────────────────────────────────────────────────
log ""
log "======================================================================"
log " Provisioning complete!"
log "======================================================================"
log ""
log " Next steps:"
log " 1. Fill in .env secrets:"
log "      sudo -u $SDRUSER nano $INSTALL_PREFIX/.env"
log "      (Set ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)"
log ""
log " 2. Connect the RSP1B to a USB 3.0 port."
log ""
log " 3. Start the agent:"
log "      sudo systemctl start sdr-agent"
log ""
log " 4. Check logs:"
log "      sudo journalctl -u sdr-agent -f"
log ""
log " 5. On Telegram, send a message to your bot to verify it responds."
log ""
log " Kill switch: sudo sdr-agent-stop"
log " Provision log: $LOG_FILE"
