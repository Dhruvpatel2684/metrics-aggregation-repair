"""TCP Connection State Recovery — Behavioral Tests.

Validates connection lifecycle invariants, pool accounting correctness,
and state machine transition validity after recovery processing.
"""

import json
import hashlib
import os

RUNTIME_DIR = "/app/runtime"
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")
STATE_PATH = os.path.join(OUTPUT_DIR, "connection_state.jsonl")
REPORT_PATH = os.path.join(OUTPUT_DIR, "recovery_report.json")

# Valid TCP state transitions per RFC-793 model
VALID_TRANSITIONS = {
    ("CLOSED", "LISTEN"),
    ("CLOSED", "SYN_SENT"),
    ("LISTEN", "SYN_RCVD"),
    ("SYN_SENT", "ESTABLISHED"),
    ("SYN_RCVD", "ESTABLISHED"),
    ("ESTABLISHED", "FIN_WAIT_1"),
    ("ESTABLISHED", "CLOSE_WAIT"),
    ("FIN_WAIT_1", "FIN_WAIT_2"),
    ("FIN_WAIT_1", "TIME_WAIT"),
    ("FIN_WAIT_2", "TIME_WAIT"),
    ("TIME_WAIT", "CLOSED"),
    ("LISTEN", "CLOSED"),
    ("SYN_RCVD", "FIN_WAIT_1"),
}


def load_state():
    """Load connection state records."""
    assert os.path.exists(STATE_PATH), f"state file missing: {STATE_PATH}"
    with open(STATE_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_report():
    """Load recovery report."""
    assert os.path.exists(REPORT_PATH), f"report file missing: {REPORT_PATH}"
    with open(REPORT_PATH) as f:
        return json.load(f)


def test_no_negative_pool_slots():
    """Pool active_count must never go negative at any point in slot history."""
    report = load_report()
    slot_history = report.get("pool_slot_history", [])
    assert len(slot_history) > 0, "no slot history recorded"

    negative_entries = []
    for entry in slot_history:
        if entry.get("active_after", 0) < 0:
            negative_entries.append(entry)

    assert len(negative_entries) == 0, (
        f"{len(negative_entries)} slot history entries with negative active_count: "
        f"{negative_entries[:3]}"
    )

    # Final pool state must also be non-negative
    pool = report.get("pool", {})
    assert pool.get("active_count", -1) >= 0, (
        f"final pool active_count is negative: {pool.get('active_count')}"
    )


def test_time_wait_duration_respected():
    """Connections that went through TIME_WAIT must have spent correct duration.

    TIME_WAIT duration is 30 seconds (from config). Connections should only
    transition TIME_WAIT->CLOSED after at least 30 seconds have elapsed.
    """
    records = load_state()
    from datetime import datetime

    for r in records:
        history = r.get("transition_history", [])
        tw_enter = None
        tw_exit = None

        for t in history:
            if t["to"] == "TIME_WAIT":
                tw_enter = t["timestamp"]
            if t["from"] == "TIME_WAIT" and t["to"] == "CLOSED":
                tw_exit = t["timestamp"]

        if tw_enter and tw_exit:
            enter_dt = datetime.fromisoformat(tw_enter.replace("Z", "+00:00"))
            exit_dt = datetime.fromisoformat(tw_exit.replace("Z", "+00:00"))
            duration = (exit_dt - enter_dt).total_seconds()

            assert duration >= 30, (
                f"conn {r['conn_id']}: TIME_WAIT duration {duration}s < 30s minimum "
                f"(entered={tw_enter}, exited={tw_exit})"
            )


def test_no_duplicate_connections():
    """Each conn_id must appear exactly once in the final state output."""
    records = load_state()
    conn_ids = [r["conn_id"] for r in records]

    from collections import Counter
    counts = Counter(conn_ids)
    duplicates = {cid: count for cid, count in counts.items() if count > 1}

    assert len(duplicates) == 0, (
        f"duplicate connection IDs in output: {duplicates}"
    )


def test_established_connections_not_evicted():
    """ESTABLISHED connections must not be force-evicted from the pool.

    Healthy connections in ESTABLISHED state should remain active regardless
    of their transition count. Forced eviction should never remove a connection
    that is still in a valid active state.
    """
    report = load_report()
    records = load_state()
    eviction_log = report.get("eviction_log", [])

    # No connection currently in ESTABLISHED should appear in eviction log
    established = {r["conn_id"] for r in records if r["state"] == "ESTABLISHED"}
    evicted_ids = {e["conn_id"] for e in eviction_log}

    wrongly_evicted = established & evicted_ids
    assert len(wrongly_evicted) == 0, (
        f"ESTABLISHED connections were force-evicted: {wrongly_evicted}"
    )

    # Additionally: there should be no evictions at all with correct processing
    assert len(eviction_log) == 0, (
        f"{len(eviction_log)} forced evictions occurred: "
        f"{[e['conn_id'] for e in eviction_log[:3]]}"
    )


def test_state_transition_validity():
    """All recorded state transitions must be valid per the TCP state model.

    No transition should go from ESTABLISHED to ESTABLISHED (duplicate ACK
    should be a no-op). All transitions must be in the valid set.
    """
    records = load_state()
    violations = []

    for r in records:
        history = r.get("transition_history", [])
        for t in history:
            pair = (t["from"], t["to"])
            if pair not in VALID_TRANSITIONS:
                violations.append({
                    "conn_id": r["conn_id"],
                    "transition": pair,
                    "event": t.get("event"),
                })

    assert len(violations) == 0, (
        f"{len(violations)} invalid state transitions: "
        f"{violations[:5]}"
    )


def test_pool_slot_accounting():
    """Pool active_count must equal the number of non-CLOSED connections.

    The final pool active_count should match the actual number of connections
    that have not yet reached CLOSED state.
    """
    records = load_state()
    report = load_report()

    non_closed = [r for r in records if r["state"] != "CLOSED"]
    pool_active = report["pool"]["active_count"]

    assert pool_active == len(non_closed), (
        f"pool active_count ({pool_active}) != non-CLOSED connections "
        f"({len(non_closed)}). States: "
        f"{[r['state'] for r in non_closed]}"
    )


def test_connection_lifecycle_complete():
    """Connections with teardown events must reach CLOSED state.

    Any connection that entered TIME_WAIT and had sufficient time for
    TIME_WAIT expiry (30s) relative to the global latest event must be CLOSED.
    """
    records = load_state()
    from datetime import datetime

    # Determine the global latest event time across all connections
    all_timestamps = []
    for r in records:
        for t in r.get("transition_history", []):
            all_timestamps.append(t["timestamp"])
    assert len(all_timestamps) > 0, "no transitions found"
    global_latest = max(all_timestamps)
    global_latest_dt = datetime.fromisoformat(global_latest.replace("Z", "+00:00"))

    incomplete = []
    for r in records:
        history = r.get("transition_history", [])
        events_seen = [t["event"] for t in history]

        # If connection entered TIME_WAIT, check if enough time passed
        # relative to the global latest event
        tw_enter_time = None
        for t in history:
            if t["to"] == "TIME_WAIT":
                tw_enter_time = t["timestamp"]

        if tw_enter_time:
            enter_dt = datetime.fromisoformat(tw_enter_time.replace("Z", "+00:00"))
            elapsed = (global_latest_dt - enter_dt).total_seconds()

            # If global time is well past TIME_WAIT entry + 30s,
            # this connection must have reached CLOSED
            if r["state"] != "CLOSED" and elapsed >= 30:
                incomplete.append({
                    "conn_id": r["conn_id"],
                    "state": r["state"],
                    "tw_elapsed_from_global": elapsed,
                })

        # Connections that received TIMEOUT should be CLOSED
        if "TIMEOUT" in events_seen and r["state"] != "CLOSED":
            incomplete.append({
                "conn_id": r["conn_id"],
                "state": r["state"],
                "reason": "received TIMEOUT but not CLOSED",
            })

    assert len(incomplete) == 0, (
        f"{len(incomplete)} connections with incomplete lifecycle: "
        f"{incomplete[:3]}"
    )


def test_event_ordering_respected():
    """No evidence of duplicate event processing in transition history.

    Each connection's transition history must show monotonically increasing
    timestamps and no repeated transitions from the same state to the same
    state (which would indicate duplicate event processing).
    """
    records = load_state()
    ordering_violations = []

    for r in records:
        history = r.get("transition_history", [])
        if len(history) < 2:
            continue

        # Check timestamp ordering
        for i in range(1, len(history)):
            prev_ts = history[i - 1]["timestamp"]
            curr_ts = history[i]["timestamp"]
            if curr_ts < prev_ts:
                ordering_violations.append({
                    "conn_id": r["conn_id"],
                    "type": "timestamp_regression",
                    "prev": prev_ts,
                    "curr": curr_ts,
                })

        # Check for self-transitions (e.g., ESTABLISHED -> ESTABLISHED)
        for t in history:
            if t["from"] == t["to"]:
                ordering_violations.append({
                    "conn_id": r["conn_id"],
                    "type": "self_transition",
                    "state": t["from"],
                    "event": t.get("event"),
                })

    assert len(ordering_violations) == 0, (
        f"{len(ordering_violations)} event ordering violations: "
        f"{ordering_violations[:5]}"
    )


def test_pool_releases_only_on_closed():
    """Pool slot releases must only happen when connection state is CLOSED.

    Early release (at FIN_WAIT_1, FIN_WAIT_2, or TIME_WAIT) violates pool
    accounting invariants and can cause negative active counts.
    """
    report = load_report()
    slot_history = report.get("pool_slot_history", [])

    early_releases = []
    for entry in slot_history:
        if entry.get("action") == "release":
            state = entry.get("state_at_release", "")
            if state != "CLOSED":
                early_releases.append(entry)

    assert len(early_releases) == 0, (
        f"{len(early_releases)} slots released before CLOSED state: "
        f"{[(e['conn_id'], e['state_at_release']) for e in early_releases[:3]]}"
    )
