#!/usr/bin/env python3
"""
Cross-reference a signal's characteristics against the local signal-reference
database, returning ranked candidate identities (or 'unknown'). Also reads the
operator content-decode policy and sets decode_allowed + the matching decoder.

Scoring (max 1.0):
  freq in [freq_min, freq_max]           0.50
  modulation family matches              0.25
  bandwidth overlaps [bw_min, bw_max]    0.15
  baud within reference range            0.10

Usage:
  identify.py --feature-vector-json '{"center_hz":433920000,"bandwidth_hz":100000,
                                       "modulation_family":"FSK","baud_estimate":4800}'
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.env import SIGNAL_REF_DB, POLICY_FILE

UNKNOWN_THRESHOLD = 0.35

# Map reference-DB category → decoder skill (Phase 2 wiring).
CATEGORY_DECODER = {
    "aviation": None,   # resolved more specifically below by modulation
    "marine": "decode_ais",
    "ism": "decode_ism",
    "ham": None,        # APRS handled specifically
    "satellite": "capture_noaa",
}
# Modulation → decoder (more specific than category)
MODULATION_DECODER = {
    "ADS-B": "decode_adsb",
    "AIS": "decode_ais",
    "ACARS": "decode_acars",
    "APRS": "decode_aprs",
}
# Decoder → content-decode policy class name
DECODER_CLASS = {
    "decode_adsb": "adsb",
    "decode_ais": "ais",
    "decode_acars": "acars",
    "decode_aprs": "aprs",
    "decode_ism": "ism",
    "capture_noaa": "noaa",
}

# Family equivalences so e.g. characterize "FM" matches reference "WFM/NFM".
FAMILY_EQUIV = {
    "FM": {"FM", "WFM", "NFM"},
    "AM": {"AM"},
    "FSK": {"FSK", "GFSK", "GMSK", "MSK", "AIS", "ACARS", "APRS", "ADS-B", "POCSAG", "FLEX"},
    "PSK": {"PSK31", "BPSK", "QPSK", "8PSK", "DQPSK", "CBOC"},
    "OFDM": {"OFDM"},
    "CW": {"CW"},
}


def _family_match(observed: str, ref_mod: str) -> bool:
    observed = (observed or "").upper()
    ref_mod = (ref_mod or "").upper()
    if observed == ref_mod:
        return True
    equiv = FAMILY_EQUIV.get(observed, {observed})
    return ref_mod in equiv


def _score(fv: dict, row: sqlite3.Row) -> float:
    score = 0.0
    center = fv.get("center_hz")
    if center is not None and row["freq_min_hz"] is not None and row["freq_max_hz"] is not None:
        if row["freq_min_hz"] <= center <= row["freq_max_hz"]:
            score += 0.50

    if _family_match(fv.get("modulation_family"), row["modulation"]):
        score += 0.25

    bw = fv.get("bandwidth_hz")
    if bw and row["bandwidth_min_hz"] and row["bandwidth_max_hz"]:
        # overlap with a tolerance factor of 2x
        if row["bandwidth_min_hz"] * 0.5 <= bw <= row["bandwidth_max_hz"] * 2.0:
            score += 0.15

    baud = fv.get("baud_estimate")
    if baud and row["baud_min"] and row["baud_max"]:
        if row["baud_min"] * 0.5 <= baud <= row["baud_max"] * 2.0:
            score += 0.10

    return round(score, 3)


def _decoder_for(row: sqlite3.Row) -> str | None:
    mod = (row["modulation"] or "").upper()
    if mod in MODULATION_DECODER:
        return MODULATION_DECODER[mod]
    if "APRS" in (row["name"] or "").upper():
        return "decode_aprs"
    if "APT" in (row["name"] or "").upper() or "NOAA" in (row["name"] or "").upper():
        return "capture_noaa"
    return CATEGORY_DECODER.get(row["category"])


def _policy_allows(decoder: str | None) -> tuple[bool, str | None]:
    if not decoder:
        return False, None
    cls = DECODER_CLASS.get(decoder)
    if not cls:
        return False, None
    try:
        policy = json.loads(POLICY_FILE.read_text())
    except Exception:
        return False, cls
    return (cls in policy.get("allowed_classes", [])), cls


def main():
    ap = argparse.ArgumentParser(description="Signal identification + policy gate")
    ap.add_argument("--feature-vector-json", required=True)
    ap.add_argument("--top-n", type=int, default=5)
    args = ap.parse_args()

    fv = json.loads(args.feature_vector_json)
    if "feature_vector" in fv:
        fv = fv["feature_vector"]

    if not SIGNAL_REF_DB.exists():
        print(json.dumps({"error": "signal_reference_db_missing",
                          "path": str(SIGNAL_REF_DB),
                          "tip": "Run db/populate_signal_reference.py"}))
        sys.exit(1)

    conn = sqlite3.connect(str(SIGNAL_REF_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM signal_types").fetchall()
    conn.close()

    scored = []
    for row in rows:
        s = _score(fv, row)
        if s > 0:
            scored.append((s, row))
    scored.sort(key=lambda t: t[0], reverse=True)

    candidates = []
    for s, row in scored[:args.top_n]:
        candidates.append({
            "name": row["name"],
            "score": s,
            "category": row["category"],
            "modulation": row["modulation"],
            "notes": row["notes"],
        })

    if not candidates or candidates[0]["score"] < UNKNOWN_THRESHOLD:
        print(json.dumps({
            "status": "unknown",
            "identity_top": None,
            "identity_score": candidates[0]["score"] if candidates else 0.0,
            "candidates": candidates,
            "tracking_recommendation": "track",
            "decode_allowed": False,
        }, ensure_ascii=False, indent=2))
        return

    top_row = scored[0][1]
    decoder = _decoder_for(top_row)
    allowed, cls = _policy_allows(decoder)

    print(json.dumps({
        "status": "identified",
        "identity_top": candidates[0]["name"],
        "identity_score": candidates[0]["score"],
        "candidates": candidates,
        "decode_class": cls,
        "decoder": decoder if allowed else None,
        "decode_allowed": allowed,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
