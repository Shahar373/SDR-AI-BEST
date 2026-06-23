#!/usr/bin/env python3
"""
Modulation/type classifier behind a stable JSON contract.

Phase 1: --backend heuristic (rules over the feature vector).
Phase 5: --backend hailo (Hailo-accelerated AMC), same output schema.

Usage:
  classify_signal.py --feature-vector-json '{"modulation_family":"FSK",...}'
  classify_signal.py --feature-vector-file /tmp/fv.json
  classify_signal.py --backend hailo --feature-vector-json '...'
"""
import argparse
import json
import sys
from pathlib import Path


def _heuristic(fv: dict) -> dict:
    family = (fv.get("modulation_family") or "UNKNOWN").upper()
    bw = fv.get("bandwidth_hz") or 0
    baud = fv.get("baud_estimate")
    kind = fv.get("kind")
    base_conf = float(fv.get("confidence", 0.5))

    classification = family
    alternatives = []

    if family == "FSK":
        if bw and bw < 25_000:
            classification = "FSK_NARROWBAND"
        elif bw and bw >= 25_000:
            classification = "FSK_WIDEBAND"
        alternatives = [{"classification": "GFSK", "confidence": round(base_conf * 0.3, 2)},
                        {"classification": "MSK", "confidence": round(base_conf * 0.15, 2)}]
    elif family == "FM":
        classification = "WFM" if bw and bw > 100_000 else "NFM"
        alternatives = [{"classification": "FSK", "confidence": round(base_conf * 0.2, 2)}]
    elif family == "AM":
        classification = "AM_DSB"
        alternatives = [{"classification": "SSB", "confidence": round(base_conf * 0.2, 2)}]
    elif family == "PSK":
        classification = "BPSK" if (baud and bw and bw < 2 * baud) else "PSK_GENERIC"
        alternatives = [{"classification": "QPSK", "confidence": round(base_conf * 0.4, 2)}]
    elif family == "OFDM":
        classification = "OFDM"
        alternatives = [{"classification": "DAB/DVB", "confidence": round(base_conf * 0.3, 2)}]
    elif family == "CW":
        classification = "CW"

    if kind == "burst" and family in ("FSK", "PSK"):
        alternatives.insert(0, {"classification": "burst_data", "confidence": round(base_conf * 0.5, 2)})

    return {
        "classification": classification,
        "modulation_family": family,
        "confidence": round(base_conf, 2),
        "alternatives": alternatives,
        "backend": "heuristic",
    }


def main():
    ap = argparse.ArgumentParser(description="Modulation/type classifier")
    ap.add_argument("--feature-vector-json", default=None)
    ap.add_argument("--feature-vector-file", default=None)
    ap.add_argument("--backend", choices=["heuristic", "hailo"], default="heuristic")
    args = ap.parse_args()

    if args.feature_vector_json:
        fv = json.loads(args.feature_vector_json)
    elif args.feature_vector_file:
        fv = json.loads(Path(args.feature_vector_file).read_text())
    else:
        print(json.dumps({"error": "missing_arg",
                          "detail": "provide --feature-vector-json or --feature-vector-file"}))
        sys.exit(1)

    # Some callers pass the full characterize output; unwrap if needed.
    if "feature_vector" in fv:
        fv = fv["feature_vector"]

    if args.backend == "hailo":
        # Phase 5 backend not yet available — fall back to heuristic, flag it.
        result = _heuristic(fv)
        result["backend"] = "heuristic"
        result["note"] = "hailo backend unavailable (Phase 5); used heuristic fallback"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(json.dumps(_heuristic(fv), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
