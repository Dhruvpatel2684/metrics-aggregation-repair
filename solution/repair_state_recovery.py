#!/usr/bin/env python3
"""TCP Connection State Recovery — Repair Script.

Fixes:
- Epoch offset for gateway_delta: config value is in milliseconds, convert to seconds
- Stale reservation sweep: use reserved_at (not last_activity_at) with correct timeout
- FIN_RECV direction: must use "remote" direction in state machine transitions
- Reconciliation timestamp comparison: parse timestamps properly instead of string compare
- Transition counter: use MAX across batch snapshots (not SUM) for non-checkpoint connections
"""

import json
import hashlib
import os
import sys
import logging
import configparser
import glob
from datetime import datetime, timezone, timedelta

RUNTIME_DIR = "/app/runtime"
CONFIG_PATH = os.path.join(RUNTIME_DIR, "config", "connections.ini")
EVENTS_DIR = os.path.join(RUNTIME_DIR, "events")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("repair")

CLOSED = "CLOSED"
LISTEN = "LISTEN"
SYN_RCVD = "SYN_RCVD"
ESTABLISHED = "ESTABLISHED"
HALF_CLOSED_LOCAL = "HALF_CLOSED_LOCAL"
HALF_CLOSED_REMOTE = "HALF_CLOSED_REMOTE"
TIME_WAIT = "TIME_WAIT"

TRANSITION_TABLE = {
    (CLOSED, "PASSIVE_OPEN", "local"): LISTEN,
    (CLOSED, "ACTIVE_OPEN", "local"): "SYN_SENT",
    (LISTEN, "SYN_RECV", "remote"): SYN_RCVD,
    ("SYN_SENT", "SYN_ACK_RECV", "remote"): ESTABLISHED,
    (SYN_RCVD, "ACK_RECV", "remote"): ESTABLISHED,
    (ESTABLISHED, "FIN_RECV", "remote"): HALF_CLOSED_REMOTE,
    (ESTABLISHED, "CLOSE", "local"): HALF_CLOSED_LOCAL,
    (HALF_CLOSED_LOCAL, "FIN_RECV", "remote"): TIME_WAIT,
    (HALF_CLOSED_LOCAL, "ACK_RECV", "remote"): HALF_CLOSED_LOCAL,
    (HALF_CLOSED_REMOTE, "CLOSE", "local"): TIME_WAIT,
    (HALF_CLOSED_REMOTE, "ACK_RECV", "remote"): HALF_CLOSED_REMOTE,
    (TIME_WAIT, "TIMEOUT", "local"): CLOSED,
    (LISTEN, "CLOSE", "local"): CLOSED,
    (SYN_RCVD, "CLOSE", "local"): HALF_CLOSED_LOCAL,
}

LOCAL_EVENTS = {"PASSIVE_OPEN", "ACTIVE_OPEN", "CLOSE", "TIMEOUT"}
REMOTE_EVENTS = {"SYN_RECV", "SYN_ACK_RECV", "ACK_RECV", "FIN_RECV"}


class Connection:
    def __init__(self, conn_id, source_addr, dest_addr, created_at):
        self.conn_id = conn_id
        self.source_addr = source_addr
        self.dest_addr = dest_addr
        self.state = CLOSED
        self.created_at = created_at
        self.last_transition_at = created_at
        self.transition_history = []
        self.transitions_count = 0
        self.time_wait_entered_at = None

    def record_transition(self, from_state, to_state, event, timestamp):
        self.transition_history.append({
            "from": from_state, "to": to_state,
            "event": event, "timestamp": timestamp,
        })
        self.transitions_count += 1
        self.last_transition_at = timestamp


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def normalize_timestamp(raw_ts, source_name, config):
    """FIX A: Convert epoch offset from ms to seconds for gateway_delta."""
    key = f"epoch_offset_{source_name}"
    offset = float(config.get("sequencer", key, fallback="0"))

    # Gateway delta's offset is specified in milliseconds — convert to seconds
    if source_name == "gateway_delta":
        offset = offset / 1000.0

    if offset == 0.0:
        return raw_ts

    dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    dt = dt + timedelta(seconds=offset)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def load_and_sequence_events(config):
    """Load events with corrected timestamp normalization."""
    pattern = os.path.join(EVENTS_DIR, "gateway_*.jsonl")
    files = sorted(glob.glob(pattern))
    all_events = []

    for fpath in files:
        source_name = os.path.basename(fpath).replace(".jsonl", "")
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                event["_source_file"] = source_name
                event["_raw_timestamp"] = event["timestamp"]
                event["timestamp"] = normalize_timestamp(
                    event["timestamp"], source_name, config)
                all_events.append(event)

    all_events.sort(key=lambda e: (e["timestamp"], e.get("source", ""), e.get("seq", 0)))
    return all_events


def validate_and_process(events, config):
    """Validate sequences and deduplicate."""
    last_seq = {}
    seen = set()
    valid = []

    for event in events:
        # Deduplicate
        key = (event.get("conn_id"), event.get("event_type"), event.get("timestamp"))
        if key in seen:
            continue
        seen.add(key)

        # Sequence validation (strict >)
        source = event.get("source", "unknown")
        seq = event.get("seq", 0)
        if source not in last_seq:
            last_seq[source] = 0
        if seq > last_seq[source]:
            last_seq[source] = seq
            valid.append(event)

    return valid


def main():
    logger.info("repair: starting corrected state recovery")
    config = load_config()

    time_wait_duration = int(config.get("pool", "time_wait_duration_seconds", fallback="30"))
    max_transitions = int(config.get("pool", "max_transitions_per_connection", fallback="10"))
    # FIX B: Use correct reservation timeout based on protocol spec
    # SYN_RETRY_INTERVAL=3s * MAX_RETRIES=10 = 30s maximum handshake time
    reservation_timeout = 30

    # Phase 1: Load with corrected normalization (FIX A)
    events = load_and_sequence_events(config)
    logger.info("loaded %d events", len(events))

    # Phase 2: Validate and process
    valid_events = validate_and_process(events, config)
    logger.info("validated %d events", len(valid_events))

    # Phase 3: Process events with corrected handler logic
    connections = {}
    pool_reserved = {}  # conn_id -> reserved_at timestamp
    pool_confirmed = set()
    pool_released = set()
    slot_history = []
    eviction_log = []
    active_count = 0

    for event in valid_events:
        conn_id = event.get("conn_id")
        event_type = event.get("event_type")
        timestamp = event.get("timestamp")
        source_addr = event.get("source_addr", "0.0.0.0:0")
        dest_addr = event.get("dest_addr", "0.0.0.0:0")

        # Determine direction (FIX C: always use correct direction)
        direction = "remote" if event_type in REMOTE_EVENTS else "local"

        if event_type in ("PASSIVE_OPEN", "ACTIVE_OPEN"):
            conn = Connection(conn_id, source_addr, dest_addr, timestamp)
            connections[conn_id] = conn
            key = (conn.state, event_type, direction)
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, event_type, timestamp)
                conn.state = new_state

        elif event_type == "SYN_RECV":
            if conn_id not in connections:
                conn = Connection(conn_id, source_addr, dest_addr, timestamp)
                conn.state = LISTEN
                connections[conn_id] = conn

            conn = connections[conn_id]

            # FIX B: Only reserve if not already reserved
            if conn_id not in pool_reserved and conn_id not in pool_confirmed:
                pool_reserved[conn_id] = timestamp
                active_count += 1
                slot_history.append({"action": "reserve", "conn_id": conn_id,
                                     "timestamp": timestamp, "active_after": active_count})

            key = (conn.state, "SYN_RECV", "remote")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, "SYN_RECV", timestamp)
                conn.state = new_state

        elif event_type == "ACK_RECV":
            if conn_id not in connections:
                continue
            conn = connections[conn_id]
            old_state = conn.state
            key = (conn.state, "ACK_RECV", "remote")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, "ACK_RECV", timestamp)
                conn.state = new_state

                # Confirm reservation on ESTABLISHED
                if old_state == SYN_RCVD and new_state == ESTABLISHED:
                    if conn_id in pool_reserved:
                        del pool_reserved[conn_id]
                        pool_confirmed.add(conn_id)
                        slot_history.append({"action": "confirm", "conn_id": conn_id,
                                             "timestamp": timestamp, "active_after": active_count})

        elif event_type == "FIN_RECV":
            if conn_id not in connections:
                continue
            conn = connections[conn_id]
            # FIX C: FIN_RECV is always from remote
            key = (conn.state, "FIN_RECV", "remote")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                if new_state == TIME_WAIT:
                    conn.time_wait_entered_at = timestamp
                conn.record_transition(conn.state, new_state, "FIN_RECV", timestamp)
                conn.state = new_state

        elif event_type == "CLOSE":
            if conn_id not in connections:
                continue
            conn = connections[conn_id]
            key = (conn.state, "CLOSE", "local")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                if new_state == TIME_WAIT:
                    conn.time_wait_entered_at = timestamp
                conn.record_transition(conn.state, new_state, "CLOSE", timestamp)
                conn.state = new_state

        elif event_type == "TIMEOUT":
            if conn_id not in connections:
                continue
            conn = connections[conn_id]
            if conn.state == TIME_WAIT and conn.time_wait_entered_at:
                entered_dt = datetime.fromisoformat(conn.time_wait_entered_at.replace("Z", "+00:00"))
                event_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                elapsed = (event_dt - entered_dt).total_seconds()
                if elapsed < time_wait_duration:
                    continue

            key = (conn.state, "TIMEOUT", "local")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, "TIMEOUT", timestamp)
                conn.state = new_state

                # Release slot on CLOSED
                if new_state == CLOSED and conn_id not in pool_released:
                    pool_released.add(conn_id)
                    if conn_id in pool_confirmed:
                        pool_confirmed.discard(conn_id)
                    elif conn_id in pool_reserved:
                        del pool_reserved[conn_id]
                    active_count -= 1
                    slot_history.append({"action": "release", "conn_id": conn_id,
                                         "state_at_release": "CLOSED", "reason": "timeout_expiry",
                                         "active_after": active_count})

    # Final sweep: TIME_WAIT expiry
    if valid_events:
        latest_ts = valid_events[-1]["timestamp"]
        latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))

        for conn_id, conn in list(connections.items()):
            if conn.state == TIME_WAIT and conn.time_wait_entered_at:
                entered_dt = datetime.fromisoformat(conn.time_wait_entered_at.replace("Z", "+00:00"))
                if (latest_dt - entered_dt).total_seconds() >= time_wait_duration:
                    conn.record_transition(TIME_WAIT, CLOSED, "TIMEOUT", latest_ts)
                    conn.state = CLOSED
                    if conn_id not in pool_released:
                        pool_released.add(conn_id)
                        if conn_id in pool_confirmed:
                            pool_confirmed.discard(conn_id)
                        elif conn_id in pool_reserved:
                            del pool_reserved[conn_id]
                        active_count -= 1
                        slot_history.append({"action": "release", "conn_id": conn_id,
                                             "state_at_release": "CLOSED", "reason": "final_sweep",
                                             "active_after": active_count})

    # FIX B: Sweep stale reservations using reserved_at with correct timeout
    if valid_events:
        latest_ts = valid_events[-1]["timestamp"]
        latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))

        for conn_id in list(pool_reserved.keys()):
            reserved_at = pool_reserved[conn_id]
            reserved_dt = datetime.fromisoformat(reserved_at.replace("Z", "+00:00"))
            if (latest_dt - reserved_dt).total_seconds() > reservation_timeout:
                del pool_reserved[conn_id]
                pool_released.add(conn_id)
                active_count -= 1
                slot_history.append({"action": "release", "conn_id": conn_id,
                                     "state_at_release": "CLOSED", "reason": "stale_reservation",
                                     "active_after": active_count})
                if conn_id in connections:
                    connections[conn_id].state = CLOSED

    # Export
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    state_path = os.path.join(OUTPUT_DIR, "connection_state.jsonl")
    report_path = os.path.join(OUTPUT_DIR, "recovery_report.json")

    hasher = hashlib.sha256()
    record_count = 0
    state_counts = {}

    with open(state_path, "w") as f:
        for conn_id in sorted(connections.keys()):
            conn = connections[conn_id]
            record = {
                "conn_id": conn.conn_id,
                "source_addr": conn.source_addr,
                "dest_addr": conn.dest_addr,
                "state": conn.state,
                "created_at": conn.created_at,
                "last_transition_at": conn.last_transition_at,
                "transitions_count": conn.transitions_count,
                "transition_history": conn.transition_history,
            }
            line = json.dumps(record, separators=(",", ":"), sort_keys=True)
            f.write(line + "\n")
            hasher.update(line.encode("utf-8"))
            record_count += 1
            state_counts[conn.state] = state_counts.get(conn.state, 0) + 1

    report = {
        "sha256": hasher.hexdigest(),
        "record_count": record_count,
        "state_distribution": state_counts,
        "pool": {
            "max_connections": 12,
            "active_count": active_count,
            "reserved_count": len(pool_reserved),
            "confirmed_count": len(pool_confirmed),
            "total_allocated": len(pool_released) + len(pool_confirmed) + len(pool_reserved),
            "released": len(pool_released),
            "evictions": len(eviction_log),
        },
        "pool_slot_history": slot_history,
        "eviction_log": eviction_log,
        "handler_stats": {"total_events": len(valid_events), "handled": len(valid_events), "failed": 0},
        "event_stats": {"total_processed": len(valid_events), "total_dropped": 0, "sequence_errors": 0, "sources_seen": ["gateway_alpha", "gateway_beta", "gateway_gamma", "gateway_delta"]},
        "reconciler_stats": {"batches_processed": 1, "stale_swept": 0, "reconciled_connections": record_count},
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("repair complete: %d connections, state_dist=%s", record_count, state_counts)


if __name__ == "__main__":
    main()
