"""Environment and path configuration for all SDR skill scripts."""
import os
from pathlib import Path

def _default_data_dir() -> Path:
    ssd = Path("/mnt/sdr-ssd/sdr-agent")
    if ssd.parent.is_mount():
        return ssd
    return Path.home() / "sdr-data"

SDR_DATA_DIR    = Path(os.environ.get("SDR_DATA_DIR", str(_default_data_dir())))
SDR_IQ_DIR      = Path(os.environ.get("SDR_IQ_DIR", "/dev/shm/sdr-iq"))
SDR_IQ_MAX_SECS = int(os.environ.get("SDR_IQ_MAX_SECS", "60"))
SDR_IQ_MAX_MB   = int(os.environ.get("SDR_IQ_MAX_MB", "256"))
SDR_MAX_IQ_CAPTURES_PER_CYCLE = int(os.environ.get("SDR_MAX_IQ_CAPTURES_PER_CYCLE", "5"))

SESSION_FILE      = SDR_DATA_DIR / "session" / "current.json"
DB_PATH           = SDR_DATA_DIR / "sdr-knowledge.sqlite"
SIGNAL_REF_DB     = Path(__file__).parent.parent.parent / "db" / "signal_reference.db"
ARTIFACTS_DIR     = SDR_DATA_DIR / "artifacts"
RUN_DIR           = SDR_DATA_DIR / "run"
RF_LOCK_FILE      = RUN_DIR / "rf.lock"
RF_LOCK_INFO_FILE = RUN_DIR / "rf.lock.info"
ARTICLES_DIR      = SDR_DATA_DIR / "articles"
POLICY_FILE       = Path(__file__).parent.parent.parent / "policy" / "content_decode.json"

def ensure_dirs():
    for d in [SDR_DATA_DIR, SDR_IQ_DIR, ARTIFACTS_DIR, RUN_DIR,
              SDR_DATA_DIR / "session", ARTICLES_DIR]:
        d.mkdir(parents=True, exist_ok=True)
