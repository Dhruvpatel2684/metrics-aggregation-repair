"""
Tests for the connection state recovery pipeline.
Validates that the recovery output correctly processes all gateway events
and produces consistent connection state records.
"""

import json
import os
import hashlib

RUNTIME_DIR = "/app/runtime"
OUTPUT_DIR = "/app/runtime/output"
CONNECTION_STATE_PATH = os.path.join(OUTPUT_DIR, "connection_state.jsonl")
RECOVERY_REPORT_PATH = os.path.join(OUTPUT_DIR, "recovery_report.json")


def load_connection_states():
    """Load connection states from the output JSONL file."""
    states = {}
    with open(CONNECTION_STATE_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            states[record["conn_id"]] = record
    return states


def load_recovery_report():
    """Load the recovery report JSON."""
    with open(RECOVERY_REPORT_PATH, "r") as f:
        return json.load(f)


def test_all_connections_reach_terminal_state():
    """
    Every connection in the event stream should complete its lifecycle
    and reach the CLOSED state. Connections stuck in intermediate states
    indicate failed transitions in the processing pipeline.
    """
    states = load_connection_states()
    assert len(states) == 8, f"Expected 8 connections, got {len(states)}"

    non_closed = {
        cid: rec["state"]
        for cid, rec in states.items()
        if rec["state"] != "CLOSED"
    }
    assert len(non_closed) == 0, (
        f"Connections not in CLOSED state: {non_closed}"
    )


def test_transition_counts_within_bounds():
    """
    Each connection should have a reasonable number of state transitions.
    A typical connection lifecycle has 5-7 transitions. Values significantly
    higher indicate counting errors in the reconciliation process.
    """
    report = load_recovery_report()
    counts = report["transition_counts"]

    for conn_id, count in counts.items():
        assert 3 <= count <= 8, (
            f"{conn_id} has {count} transitions, expected between 3 and 8"
        )


def test_pool_fully_released():
    """
    After all connections complete their lifecycle, no pool slots should
    remain active. All reservations should be confirmed and then released
    during connection teardown.
    """
    report = load_recovery_report()
    pool_status = report["pool_status"]

    assert pool_status["active_slots"] == 0, (
        f"Expected 0 active pool slots, got {pool_status['active_slots']}"
    )
    assert pool_status["total_tracked"] == 8, (
        f"Expected 8 total tracked connections, got {pool_status['total_tracked']}"
    )
    assert len(pool_status["leaked_reservations"]) == 0, (
        f"Leaked reservations detected: {pool_status['leaked_reservations']}"
    )


def test_no_anomalies_detected():
    """
    A correctly processed recovery should produce zero anomalies.
    Anomalies indicate state machine violations, pool inconsistencies,
    or stalled handshakes that were not properly resolved.
    """
    report = load_recovery_report()
    anomalies = report["anomalies"]

    assert len(anomalies) == 0, (
        f"Expected 0 anomalies, got {len(anomalies)}: "
        + "; ".join(f"{a['type']}({a['conn_id']})" for a in anomalies)
    )


def test_connection_state_ordering():
    """
    The connection state output file should contain records in sorted
    order by connection ID for deterministic output verification.
    """
    conn_ids = []
    with open(CONNECTION_STATE_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            conn_ids.append(record["conn_id"])

    assert conn_ids == sorted(conn_ids), (
        f"Connection states not in sorted order: {conn_ids}"
    )


def test_integrity_hash_consistency():
    """
    The integrity hash in the recovery report should match a recomputation
    from the connection state data, ensuring the hash was computed over
    the same ordered data that was exported.
    """
    states = load_connection_states()
    report = load_recovery_report()

    hasher = hashlib.sha256()
    for conn_id in sorted(states.keys()):
        record = states[conn_id]
        entry = f"{conn_id}:{record['state']}:{record['transitions_count']}"
        hasher.update(entry.encode("utf-8"))

    expected_hash = hasher.hexdigest()
    actual_hash = report["integrity_hash"]

    assert actual_hash == expected_hash, (
        f"Integrity hash mismatch: report has {actual_hash}, "
        f"recomputed is {expected_hash}"
    )


def test_conn_006_proper_lifecycle():
    """
    Connection conn_006 uses multi-path event delivery where the SYN
    and ACK arrive from different gateways. The sequencer must handle
    this correctly to allow the full handshake to complete.
    """
    states = load_connection_states()
    assert "conn_006" in states, "conn_006 not found in output"

    conn = states["conn_006"]
    assert conn["state"] == "CLOSED", (
        f"conn_006 should be CLOSED, got {conn['state']}"
    )
    assert conn["transitions_count"] == 6, (
        f"conn_006 should have 6 transitions, got {conn['transitions_count']}"
    )


def test_slow_handshake_completion():
    """
    Connection conn_005 has a 25-second handshake delay. The pool manager
    must not prematurely release its reservation during this period,
    allowing the connection to eventually confirm and complete.
    """
    states = load_connection_states()
    report = load_recovery_report()

    assert "conn_005" in states, "conn_005 not found in output"
    conn = states["conn_005"]

    assert conn["state"] == "CLOSED", (
        f"conn_005 should be CLOSED (completed lifecycle), got {conn['state']}"
    )

    # Verify conn_005 is not listed as having pool issues
    leaked = report["pool_status"]["leaked_reservations"]
    assert "conn_005" not in leaked, (
        "conn_005 should not have a leaked reservation"
    )
