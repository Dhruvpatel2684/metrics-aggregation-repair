"""TCP Connection State Recovery — Behavioral Tests.

Validates connection lifecycle invariants, pool accounting correctness,
state machine transition validity, and reconciliation integrity.
"""

import json
import hashlib
import os
from datetime import datetime
from collections import Counter

RUNTIME_DIR = "/app/runtime"
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")
STATE_PATH = os.path.join(OUTPUT_DIR, "connection_state.jsonl")
REPORT_PATH = os.path.join(OUTPUT_DIR, "recovery_report.json")

VALID_STATES = {"CLOSED", "LISTEN", "SYN_SENT", "SYN_RCVD", "ESTABLISHED",
                "HALF_CLOSED_LOCAL", "HALF_CLOSED_REMOTE", "TIME_WAIT"}

VALID_TRANSITIONS = {
    ("CLOSED", "LISTEN"),
    ("CLOSED", "SYN_SENT"),
    ("LISTEN", "SYN_RCVD"),
    ("SYN_SENT", "ESTABLISHED"),
    ("SYN_RCVD", "ESTABLISHED"),
    ("ESTABLISHED", "HALF_CLOSED_LOCAL"),
    ("ESTABLISHED", "HALF_CLOSED_REMOTE"),
    ("HALF_CLOSED_LOCAL", "TIME_WAIT"),
    ("HALF_CLOSED_REMOTE", "TIME_WAIT"),
    ("HALF_CLOSED_LOCAL", "HALF_CLOSED_LOCAL"),
    ("HALF_CLOSED_REMOTE", "HALF_CLOSED_REMOTE"),
    ("TIME_WAIT", "CLOSED"),
    ("LISTEN", "CLOSED"),
    ("SYN_RCVD", "HALF_CLOSED_LOCAL"),
}


def load_state():
    assert os.path.exists(STATE_PATH), f"missing: {STATE_PATH}"
    with open(STATE_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_report():
    assert os.path.exists(REPORT_PATH), f"missing: {REPORT_PATH}"
    with open(REPORT_PATH) as f:
        return json.load(f)


def test_no_negative_pool_slots():
    """Pool active_count must never go negative at any point in slot history."""
    report = load_report()
    slot_history = report.get("pool_slot_history", [])
    assert len(slot_history) > 0, "no slot history"

    for entry in slot_history:
        assert entry.get("active_after", 0) >= 0, (
            f"negative pool count: {entry}")

    pool = report["pool"]
    assert pool["active_count"] >= 0
    assert pool["reserved_count"] >= 0
    assert pool["confirmed_count"] >= 0


def test_pool_slot_accounting():
    """Pool active_count must equal non-CLOSED connections. No slot leaks."""
    records = load_state()
    report = load_report()

    non_closed = [r for r in records if r["state"] != "CLOSED"]
    pool = report["pool"]

    # Active count should match actual non-closed connections
    assert pool["active_count"] == len(non_closed), (
        f"pool active={pool['active_count']} but {len(non_closed)} non-CLOSED "
        f"connections. States: {[r['state'] for r in non_closed]}")

    # No leaked reservations — reserved_count should be 0 at end
    assert pool["reserved_count"] == 0, (
        f"leaked reservations: reserved_count={pool['reserved_count']}")


def test_half_closed_symmetry():
    """Connections must reach CLOSED through proper half-close sequences.

    Every connection that has both FIN_RECV and CLOSE events in its source
    data must show proper half-close state transitions. The system must
    handle both passive close (FIN from remote) and active close (local CLOSE).
    At least some connections must show HALF_CLOSED_REMOTE in their history.
    """
    records = load_state()

    # Count half-close directions seen
    local_count = 0
    remote_count = 0

    for r in records:
        for t in r.get("transition_history", []):
            if t["to"] == "HALF_CLOSED_LOCAL":
                local_count += 1
            elif t["to"] == "HALF_CLOSED_REMOTE":
                remote_count += 1

    # The event data contains both passive close (FIN before CLOSE) and
    # active close (CLOSE before FIN). Both directions must appear.
    assert remote_count > 0, (
        f"no HALF_CLOSED_REMOTE transitions found (only {local_count} LOCAL). "
        f"Passive close (remote FIN) is not being handled correctly.")

    assert local_count > 0, (
        f"no HALF_CLOSED_LOCAL transitions found (only {remote_count} REMOTE). "
        f"Active close (local CLOSE) is not being handled correctly.")


def test_reservation_lifecycle():
    """All reserved slots must either confirm or be swept. No leaked reservations."""
    report = load_report()
    pool = report["pool"]

    # At end of processing, all reservations should be resolved
    assert pool["reserved_count"] == 0, (
        f"unresolved reservations: {pool['reserved_count']} "
        f"(should be 0 — all must confirm or be swept)")

    # Total = released + still-active (confirmed)
    non_closed_count = pool["confirmed_count"]
    released_count = pool["released"]
    total = non_closed_count + released_count

    assert total == pool["total_allocated"], (
        f"slot accounting mismatch: confirmed({non_closed_count}) + "
        f"released({released_count}) != allocated({pool['total_allocated']})")


def test_event_temporal_consistency():
    """All transitions must have monotonically increasing timestamps."""
    records = load_state()
    violations = []

    for r in records:
        history = r.get("transition_history", [])
        for i in range(1, len(history)):
            prev_ts = history[i-1]["timestamp"]
            curr_ts = history[i]["timestamp"]
            if curr_ts < prev_ts:
                violations.append({
                    "conn_id": r["conn_id"],
                    "prev": prev_ts,
                    "curr": curr_ts,
                })

    assert len(violations) == 0, (
        f"{len(violations)} timestamp ordering violations: {violations[:3]}")


def test_transition_count_bounds():
    """No connection may exceed max_transitions without being evicted.

    If a connection's transitions_count exceeds the configured maximum (10),
    it must appear in the eviction log OR the count must be within bounds.
    """
    records = load_state()
    report = load_report()
    max_transitions = 10  # from config

    evicted_ids = {e["conn_id"] for e in report.get("eviction_log", [])}
    violations = []

    for r in records:
        if r["transitions_count"] > max_transitions:
            if r["conn_id"] not in evicted_ids:
                violations.append({
                    "conn_id": r["conn_id"],
                    "transitions": r["transitions_count"],
                    "max": max_transitions,
                })

    assert len(violations) == 0, (
        f"{len(violations)} connections exceed max_transitions without eviction: "
        f"{violations[:3]}")


def test_export_integrity():
    """SHA-256 in report must match recomputation from state file."""
    report = load_report()

    with open(STATE_PATH) as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]

    hasher = hashlib.sha256()
    for line in lines:
        hasher.update(line.encode("utf-8"))

    computed_hash = hasher.hexdigest()
    reported_hash = report.get("sha256", "")

    assert computed_hash == reported_hash, (
        f"hash mismatch: computed={computed_hash[:16]}... "
        f"reported={reported_hash[:16]}...")


def test_connection_id_format():
    """All connection IDs must use canonical format 'conn_NNN'."""
    records = load_state()
    invalid = []

    for r in records:
        conn_id = r["conn_id"]
        if ":" in conn_id or not conn_id.startswith("conn_"):
            invalid.append(conn_id)

    assert len(invalid) == 0, (
        f"non-canonical connection IDs: {invalid}")


def test_connection_lifecycle_complete():
    """Connections with close events must complete their lifecycle to CLOSED.

    Any connection that has both FIN_RECV and CLOSE events must eventually
    reach TIME_WAIT and then CLOSED. Connections stuck in intermediate
    states indicate broken transition handling.
    """
    records = load_state()
    report = load_report()

    # Get the event stats to know how many connections had close events
    incomplete = []
    for r in records:
        history = r.get("transition_history", [])
        events_seen = {t["event"] for t in history}

        # If connection had a CLOSE event, it should complete lifecycle
        if "CLOSE" in events_seen and r["state"] not in ("CLOSED", "TIME_WAIT", "ESTABLISHED"):
            # Stuck in half-closed without progressing
            if r["state"] in ("HALF_CLOSED_LOCAL", "HALF_CLOSED_REMOTE"):
                # Check if there's a matching FIN/CLOSE to complete
                # A HALF_CLOSED connection with both CLOSE and FIN should reach TIME_WAIT
                if "FIN_RECV" in events_seen or "CLOSE" in events_seen:
                    incomplete.append({
                        "conn_id": r["conn_id"],
                        "state": r["state"],
                        "events": sorted(events_seen),
                    })

    # Also check: connections that entered TIME_WAIT with sufficient time should be CLOSED
    all_ts = []
    for r in records:
        for t in r.get("transition_history", []):
            all_ts.append(t["timestamp"])
    if all_ts:
        global_latest = max(all_ts)
        global_dt = datetime.fromisoformat(global_latest.replace("Z", "+00:00"))

        for r in records:
            for t in r.get("transition_history", []):
                if t["to"] == "TIME_WAIT":
                    enter_dt = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
                    elapsed = (global_dt - enter_dt).total_seconds()
                    if elapsed >= 30 and r["state"] != "CLOSED":
                        incomplete.append({
                            "conn_id": r["conn_id"],
                            "state": r["state"],
                            "reason": "TIME_WAIT expired but not CLOSED",
                        })

    assert len(incomplete) == 0, (
        f"{len(incomplete)} connections with incomplete lifecycle: {incomplete[:3]}")


def test_state_transition_validity():
    """All recorded transitions must be valid per the TCP state model."""
    records = load_state()
    violations = []

    for r in records:
        for t in r.get("transition_history", []):
            pair = (t["from"], t["to"])
            if pair not in VALID_TRANSITIONS:
                violations.append({
                    "conn_id": r["conn_id"],
                    "transition": pair,
                    "event": t.get("event"),
                })

    assert len(violations) == 0, (
        f"{len(violations)} invalid transitions: {violations[:5]}")
