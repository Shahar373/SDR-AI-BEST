#!/usr/bin/env python3
"""
The only writer/reader interface to the spectrum knowledge base.

Subcommands:
  upsert --observation-json '{...}'   Insert/update a signal + observation.
  query  [filters]                    Read back signals from the catalog.

Upsert observation JSON fields (all optional except center_hz):
  center_hz, bandwidth_hz, modulation_family, baud_estimate, kind,
  identity_top, identity_score, identity_candidates, status, snr,
  feature_vector, decoder_output, artifact_path

Usage:
  catalog.py upsert --observation-json '{"center_hz":433920000,...}'
  catalog.py query --min-hz 430000000 --max-hz 440000000
  catalog.py query --status unknown
  catalog.py query --last-hours 24
  catalog.py query --emitter-key "433920000_FSK"
  catalog.py query --from 2026-06-23T00:00:00Z --to 2026-06-23T23:59:59Z
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import db, session_store


def _emitter_key(center_hz: float, modulation: str) -> str:
    return f"{int(round(center_hz, -3))}_{(modulation or 'UNKNOWN').upper()}"


def cmd_upsert(args) -> None:
    obs = json.loads(args.observation_json)
    center_hz = obs.get("center_hz")
    if center_hz is None:
        print(json.dumps({"error": "missing_field", "detail": "center_hz is required"}))
        sys.exit(1)

    modulation = obs.get("modulation_family", "UNKNOWN")
    emitter_key = _emitter_key(center_hz, modulation)
    now = datetime.now(timezone.utc).isoformat()

    session = session_store.read()
    session_id = (session or {}).get("session_id", "no-session")

    conn = db.get_conn()
    existing = conn.execute(
        "SELECT id, observation_count FROM signals WHERE emitter_key=?",
        (emitter_key,)).fetchone()

    candidates_json = json.dumps(obs.get("identity_candidates", []), ensure_ascii=False)
    status = obs.get("status", "unknown")

    if existing:
        signal_id = existing["id"]
        new_count = existing["observation_count"] + 1
        # COALESCE keeps the prior value when this observation omits a field.
        conn.execute(
            "UPDATE signals SET last_seen=?, "
            "center_hz=COALESCE(?, center_hz), "
            "bandwidth_hz=COALESCE(?, bandwidth_hz), "
            "modulation_family=COALESCE(?, modulation_family), "
            "baud_estimate=COALESCE(?, baud_estimate), "
            "kind=COALESCE(?, kind), "
            "identity_top=COALESCE(?, identity_top), "
            "identity_score=COALESCE(?, identity_score), "
            "identity_candidates_json=?, status=?, observation_count=? "
            "WHERE id=?",
            (now, center_hz, obs.get("bandwidth_hz"), obs.get("modulation_family"),
             obs.get("baud_estimate"), obs.get("kind"), obs.get("identity_top"),
             obs.get("identity_score"), candidates_json, status, new_count, signal_id))
        action = "updated"
    else:
        signal_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO signals (id, emitter_key, first_seen, last_seen, center_hz, "
            "bandwidth_hz, modulation_family, baud_estimate, kind, identity_top, "
            "identity_score, identity_candidates_json, status, observation_count) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (signal_id, emitter_key, now, now, center_hz,
             obs.get("bandwidth_hz") if obs.get("bandwidth_hz") is not None else 0.0,
             modulation, obs.get("baud_estimate"), obs.get("kind"),
             obs.get("identity_top"), obs.get("identity_score"),
             candidates_json, status))
        action = "inserted"
        new_count = 1

    # Insert observation row
    obs_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO observations (id, signal_id, session_id, timestamp, snr, "
        "feature_vector_json, artifact_path, decoder_output_json) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (obs_id, signal_id, session_id, now, obs.get("snr"),
         json.dumps(obs.get("feature_vector"), ensure_ascii=False) if obs.get("feature_vector") else None,
         obs.get("artifact_path"),
         json.dumps(obs.get("decoder_output"), ensure_ascii=False) if obs.get("decoder_output") else None))

    # Optional artifact linkage
    if obs.get("artifact_path"):
        conn.execute(
            "INSERT INTO artifacts (id, observation_id, kind, path, created_at) "
            "VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), obs_id, obs.get("artifact_kind", "iq_capture"),
             obs["artifact_path"], now))

    conn.commit()
    conn.close()

    print(json.dumps({
        "status": "ok",
        "action": action,
        "signal_id": signal_id,
        "observation_id": obs_id,
        "emitter_key": emitter_key,
        "observation_count": new_count,
    }, ensure_ascii=False, indent=2))


def cmd_query(args) -> None:
    conn = db.get_conn()
    where = []
    params = []

    if args.min_hz is not None:
        where.append("center_hz >= ?"); params.append(args.min_hz)
    if args.max_hz is not None:
        where.append("center_hz <= ?"); params.append(args.max_hz)
    if args.status:
        where.append("status = ?"); params.append(args.status)
    if args.emitter_key:
        where.append("emitter_key = ?"); params.append(args.emitter_key)
    if args.last_hours is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=args.last_hours)).isoformat()
        where.append("last_seen >= ?"); params.append(cutoff)
    if args.from_ts:
        where.append("last_seen >= ?"); params.append(args.from_ts)
    if args.to_ts:
        where.append("first_seen <= ?"); params.append(args.to_ts)

    sql = "SELECT * FROM signals"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY center_hz ASC LIMIT ?"
    params.append(args.limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    signals = []
    for r in rows:
        d = dict(r)
        if d.get("identity_candidates_json"):
            try:
                d["identity_candidates"] = json.loads(d.pop("identity_candidates_json"))
            except Exception:
                d["identity_candidates"] = []
        signals.append(d)

    print(json.dumps({
        "count": len(signals),
        "signals": signals,
    }, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Spectrum knowledge base interface")
    sub = ap.add_subparsers(dest="command", required=True)

    p_up = sub.add_parser("upsert")
    p_up.add_argument("--observation-json", required=True)

    p_q = sub.add_parser("query")
    p_q.add_argument("--min-hz", type=float, default=None)
    p_q.add_argument("--max-hz", type=float, default=None)
    p_q.add_argument("--status", default=None)
    p_q.add_argument("--emitter-key", default=None)
    p_q.add_argument("--last-hours", type=float, default=None)
    p_q.add_argument("--from", dest="from_ts", default=None)
    p_q.add_argument("--to", dest="to_ts", default=None)
    p_q.add_argument("--limit", type=int, default=200)

    args = ap.parse_args()
    if args.command == "upsert":
        cmd_upsert(args)
    elif args.command == "query":
        cmd_query(args)


if __name__ == "__main__":
    main()
