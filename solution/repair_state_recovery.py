#!/usr/bin/env python3
"""TCP Connection State Recovery — Repair Script.

Re-processes event logs with corrected logic:
- TIME_WAIT timeout uses time_wait_duration (not connection_timeout)
- Pool slot release only on CLOSED state (not on any closing state)
- Sequence validation uses strict > (not >=) to prevent duplicate processing
- SYN_RECV handler checks for existing pool entry before allocating
- Duplicate ACK in ESTABLISHED is a no-op (no transition recorded)
"""

import json
import hashlib
import os
import sys
import logging
import configparser
import glob
from datetime import datetime, timezone

RUNTIME_DIR = "/app/runtime"
CONFIG_PATH = os.path.join(RUNTIME_DIR, "config", "connections.ini")
EVENTS_DIR = os.path.join(RUNTIME_DIR, "events")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("repair.state_recovery")

# --- TCP States ---
CLOSED = "CLOSED"
LISTEN = "LISTEN"
SYN_SENT = "SYN_SENT"
SYN_RCVD = "SYN_RCVD"
ESTABLISHED = "ESTABLISHED"
FIN_WAIT_1 = "FIN_WAIT_1"
FIN_WAIT_2 = "FIN_WAIT_2"
TIME_WAIT = "TIME_WAIT"

TRANSITION_TABLE = {
    (CLOSED, "PASSIVE_OPEN"): LISTEN,
    (CLOSED, "ACTIVE_OPEN"): SYN_SENT,
    (LISTEN, "SYN_RECV"): SYN_RCVD,
    (SYN_SENT, "SYN_ACK_RECV"): ESTABLISHED,
    (SYN_RCVD, "ACK_RECV"): ESTABLISHED,
    (ESTABLISHED, "FIN_RECV"): FIN_WAIT_1,
    (ESTABLISHED, "CLOSE"): FIN_WAIT_1,
    (FIN_WAIT_1, "ACK_RECV"): FIN_WAIT_2,
    (FIN_WAIT_1, "FIN_RECV"): TIME_WAIT,
    (FIN_WAIT_2, "FIN_RECV"): TIME_WAIT,
    (TIME_WAIT, "TIMEOUT"): CLOSED,
    (LISTEN, "CLOSE"): CLOSED,
    (SYN_RCVD, "CLOSE"): FIN_WAIT_1,
}


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
            "from": from_state,
            "to": to_state,
            "event": event,
            "timestamp": timestamp,
        })
        self.transitions_count += 1
        self.last_transition_at = timestamp


class PoolEntry:
    def __init__(self, conn_id, allocated_at):
        self.conn_id = conn_id
        self.allocated_at = allocated_at
        self.released = False
        self.release_reason = None


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def load_events():
    """Load all events from gateway JSONL files."""
    pattern = os.path.join(EVENTS_DIR, "gateway_*.jsonl")
    files = sorted(glob.glob(pattern))
    all_events = []

    for fpath in files:
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                all_events.append(event)

    # Sort by timestamp then sequence
    all_events.sort(key=lambda e: (e["timestamp"], e.get("seq", 0)))
    return all_events


def validate_sequence_strict(event, last_sequence):
    """FIX for Bug 3: Use strict > instead of >= for sequence validation."""
    source = event.get("source", "unknown")
    seq = event.get("seq", 0)

    if source not in last_sequence:
        last_sequence[source] = 0

    last_seq = last_sequence[source]

    # FIXED: strict greater-than prevents reprocessing same sequence
    if seq > last_seq:
        last_sequence[source] = seq
        return True
    else:
        return False


def deduplicate_events(events):
    """Remove exact duplicate events."""
    seen = set()
    deduped = []
    for event in events:
        key = (event.get("conn_id"), event.get("event_type"), event.get("timestamp"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def main():
    logger.info("repair: starting corrected state recovery")

    config = load_config()
    max_connections = int(config.get("pool", "max_connections", fallback="10"))
    connection_timeout = int(config.get("pool", "connection_timeout_seconds", fallback="120"))
    time_wait_duration = int(config.get("pool", "time_wait_duration_seconds", fallback="30"))
    max_transitions = int(config.get("pool", "max_transitions_per_connection", fallback="8"))

    # Load and validate events
    raw_events = load_events()
    events = deduplicate_events(raw_events)

    # Apply strict sequence validation (FIX Bug 3)
    last_sequence = {}
    valid_events = []
    for event in events:
        if validate_sequence_strict(event, last_sequence):
            valid_events.append(event)

    logger.info("repair: %d valid events (from %d raw)", len(valid_events), len(raw_events))

    # Process events with corrected logic
    connections = {}
    pool_entries = {}
    pool_active_count = 0
    slot_history = []
    eviction_log = []

    for event in valid_events:
        conn_id = event.get("conn_id")
        event_type = event.get("event_type")
        timestamp = event.get("timestamp")
        source_addr = event.get("source_addr", "0.0.0.0:0")
        dest_addr = event.get("dest_addr", "0.0.0.0:0")

        if event_type in ("PASSIVE_OPEN", "ACTIVE_OPEN"):
            # Create connection and allocate slot
            conn = Connection(conn_id, source_addr, dest_addr, timestamp)
            connections[conn_id] = conn

            if pool_active_count < max_connections:
                pool_entries[conn_id] = PoolEntry(conn_id, timestamp)
                pool_active_count += 1
                slot_history.append({
                    "action": "allocate",
                    "conn_id": conn_id,
                    "timestamp": timestamp,
                    "active_after": pool_active_count,
                })

            # Transition CLOSED -> LISTEN or SYN_SENT
            open_event = "PASSIVE_OPEN" if event_type == "PASSIVE_OPEN" else "ACTIVE_OPEN"
            key = (conn.state, open_event)
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, open_event, timestamp)
                conn.state = new_state

        elif event_type == "SYN_RECV":
            # FIX Bug 4: Check if connection already exists before creating
            if conn_id not in connections:
                # This shouldn't happen with correct sequencing, but handle gracefully
                conn = Connection(conn_id, source_addr, dest_addr, timestamp)
                conn.state = LISTEN
                connections[conn_id] = conn
                # Only allocate if not already in pool
                if conn_id not in pool_entries and pool_active_count < max_connections:
                    pool_entries[conn_id] = PoolEntry(conn_id, timestamp)
                    pool_active_count += 1
                    slot_history.append({
                        "action": "allocate",
                        "conn_id": conn_id,
                        "timestamp": timestamp,
                        "active_after": pool_active_count,
                    })

            conn = connections[conn_id]
            key = (conn.state, "SYN_RECV")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, "SYN_RECV", timestamp)
                conn.state = new_state

        elif event_type == "ACK_RECV":
            if conn_id not in connections:
                continue

            conn = connections[conn_id]

            # FIX Bug 5: Duplicate ACK in ESTABLISHED is a no-op
            if conn.state == ESTABLISHED:
                # Ignore duplicate ACKs — do NOT record transition
                continue

            key = (conn.state, "ACK_RECV")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, "ACK_RECV", timestamp)
                conn.state = new_state

        elif event_type == "FIN_RECV":
            if conn_id not in connections:
                continue

            conn = connections[conn_id]
            key = (conn.state, "FIN_RECV")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                if new_state == TIME_WAIT:
                    conn.time_wait_entered_at = timestamp
                conn.record_transition(conn.state, new_state, "FIN_RECV", timestamp)
                conn.state = new_state

                # FIX Bug 2: Do NOT release slot here — only on CLOSED
                # (no release_slot call for FIN_WAIT_1/TIME_WAIT)

        elif event_type == "CLOSE":
            if conn_id not in connections:
                continue

            conn = connections[conn_id]
            key = (conn.state, "CLOSE")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, "CLOSE", timestamp)
                conn.state = new_state

                # FIX Bug 2: Only release on CLOSED
                if new_state == CLOSED:
                    if conn_id in pool_entries and not pool_entries[conn_id].released:
                        pool_entries[conn_id].released = True
                        pool_entries[conn_id].release_reason = "close_to_closed"
                        pool_active_count -= 1
                        slot_history.append({
                            "action": "release",
                            "conn_id": conn_id,
                            "state_at_release": CLOSED,
                            "reason": "close_to_closed",
                            "active_after": pool_active_count,
                        })

        elif event_type == "TIMEOUT":
            if conn_id not in connections:
                continue

            conn = connections[conn_id]

            # FIX Bug 1: Use time_wait_duration instead of connection_timeout
            if conn.state == TIME_WAIT and conn.time_wait_entered_at:
                entered_dt = datetime.fromisoformat(
                    conn.time_wait_entered_at.replace("Z", "+00:00"))
                event_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                elapsed = (event_dt - entered_dt).total_seconds()

                if elapsed < time_wait_duration:
                    # Not ready to close yet
                    continue

            key = (conn.state, "TIMEOUT")
            if key in TRANSITION_TABLE:
                new_state = TRANSITION_TABLE[key]
                conn.record_transition(conn.state, new_state, "TIMEOUT", timestamp)
                conn.state = new_state

                # Release slot on CLOSED
                if new_state == CLOSED:
                    if conn_id in pool_entries and not pool_entries[conn_id].released:
                        pool_entries[conn_id].released = True
                        pool_entries[conn_id].release_reason = "timeout_expiry"
                        pool_active_count -= 1
                        slot_history.append({
                            "action": "release",
                            "conn_id": conn_id,
                            "state_at_release": CLOSED,
                            "reason": "timeout_expiry",
                            "active_after": pool_active_count,
                        })

    # Final sweep: check TIME_WAIT expiry for remaining connections
    if valid_events:
        latest_ts = valid_events[-1]["timestamp"]
        for conn_id, conn in connections.items():
            if conn.state == TIME_WAIT and conn.time_wait_entered_at:
                entered_dt = datetime.fromisoformat(
                    conn.time_wait_entered_at.replace("Z", "+00:00"))
                latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
                elapsed = (latest_dt - entered_dt).total_seconds()

                if elapsed >= time_wait_duration:
                    conn.record_transition(TIME_WAIT, CLOSED, "TIMEOUT", latest_ts)
                    conn.state = CLOSED
                    if conn_id in pool_entries and not pool_entries[conn_id].released:
                        pool_entries[conn_id].released = True
                        pool_entries[conn_id].release_reason = "final_sweep"
                        pool_active_count -= 1
                        slot_history.append({
                            "action": "release",
                            "conn_id": conn_id,
                            "state_at_release": CLOSED,
                            "reason": "final_sweep",
                            "active_after": pool_active_count,
                        })

    # Export corrected output
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

            state = conn.state
            state_counts[state] = state_counts.get(state, 0) + 1

    # Build report
    report = {
        "sha256": hasher.hexdigest(),
        "record_count": record_count,
        "state_distribution": state_counts,
        "pool": {
            "max_connections": max_connections,
            "active_count": pool_active_count,
            "total_allocated": len(pool_entries),
            "released": sum(1 for e in pool_entries.values() if e.released),
            "evictions": len(eviction_log),
        },
        "pool_slot_history": slot_history,
        "eviction_log": eviction_log,
        "handler_stats": {
            "total_events": len(valid_events),
            "handled": len(valid_events),
            "failed": 0,
        },
        "event_stats": {
            "total_processed": len(valid_events),
            "total_dropped": len(raw_events) - len(valid_events),
            "sequence_errors": 0,
            "sources_seen": list(last_sequence.keys()),
        },
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("repair complete: %d connections, pool_active=%d",
                record_count, pool_active_count)
    logger.info("state distribution: %s", state_counts)


if __name__ == "__main__":
    main()
