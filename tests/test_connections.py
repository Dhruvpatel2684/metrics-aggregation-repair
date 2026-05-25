"""TCP Connection State Recovery — Behavioral Tests.

These tests execute the runtime directly and validate invariants on the output.
The runtime code under /app/runtime/ must be fixed in-place for tests to pass.
"""

import json
import hashlib
import os
import sys
import subprocess

RUNTIME_DIR = "/app/runtime"
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")
STATE_PATH = os.path.join(OUTPUT_DIR, "connection_state.jsonl")
REPORT_PATH = os.path.join(OUTPUT_DIR, "recovery_report.json")


def _run_recovery():
    """Execute the runtime and produce fresh output."""
    # Remove stale output
    for f in [STATE_PATH, REPORT_PATH]:
        if os.path.exists(f):
            os.remove(f)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(RUNTIME_DIR)
    result = subprocess.run(
        [sys.executable, os.path.join(RUNTIME_DIR, "run_recovery.py")],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"runtime failed: {result.stderr[-500:]}"


def _load_state():
    if not os.path.exists(STATE_PATH):
        _run_recovery()
    with open(STATE_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_report():
    if not os.path.exists(REPORT_PATH):
        _run_recovery()
    with open(REPORT_PATH) as f:
        return json.load(f)


def setup_module(module):
    """Run recovery once before all tests."""
    _run_recovery()


def test_pool_no_leaked_reservations():
    """All reserved slots must be confirmed or swept. reserved_count must be 0."""
    report = _load_report()
    pool = report["pool"]
    assert pool["reserved_count"] == 0, (
        f"leaked reservations: reserved_count={pool['reserved_count']} "
        f"(all must confirm or be swept)")


def test_pool_active_matches_non_closed():
    """Pool active_count must equal number of non-CLOSED connections."""
    records = _load_state()
    report = _load_report()
    non_closed = [r for r in records if r["state"] != "CLOSED"]
    pool = report["pool"]
    assert pool["active_count"] == len(non_closed), (
        f"pool active={pool['active_count']} but {len(non_closed)} non-CLOSED. "
        f"States: {[r['state'] for r in non_closed]}")


def test_half_closed_both_directions():
    """Both HALF_CLOSED_LOCAL and HALF_CLOSED_REMOTE must appear in transition histories.

    The event data contains both passive close (FIN first) and active close
    (CLOSE first). Both half-close directions must be correctly handled.
    """
    records = _load_state()
    local_seen = False
    remote_seen = False
    for r in records:
        for t in r.get("transition_history", []):
            if t["to"] == "HALF_CLOSED_LOCAL":
                local_seen = True
            elif t["to"] == "HALF_CLOSED_REMOTE":
                remote_seen = True

    assert remote_seen, (
        "no HALF_CLOSED_REMOTE transitions found — passive close (remote FIN) broken")
    assert local_seen, (
        "no HALF_CLOSED_LOCAL transitions found — active close (local CLOSE) broken")


def test_transition_counts_within_bounds():
    """No connection may have transitions_count > max (10) without eviction."""
    records = _load_state()
    report = _load_report()
    max_t = 10
    evicted = {e["conn_id"] for e in report.get("eviction_log", [])}
    violations = []
    for r in records:
        if r["transitions_count"] > max_t and r["conn_id"] not in evicted:
            violations.append((r["conn_id"], r["transitions_count"]))
    assert len(violations) == 0, (
        f"transition count violations (max={max_t}): {violations[:5]}")


def test_no_negative_pool_counts():
    """Pool counts must never go negative in slot history."""
    report = _load_report()
    for entry in report.get("pool_slot_history", []):
        assert entry.get("active_after", 0) >= 0, (
            f"negative pool count: {entry}")


def test_closed_connections_have_timeout():
    """Every CLOSED connection must have a TIMEOUT transition in its history."""
    records = _load_state()
    violations = []
    for r in records:
        if r["state"] == "CLOSED":
            events = [t["event"] for t in r.get("transition_history", [])]
            if "TIMEOUT" not in events:
                violations.append(r["conn_id"])
    assert len(violations) == 0, (
        f"CLOSED connections without TIMEOUT: {violations}")


def test_time_wait_before_closed():
    """Every CLOSED connection must have transitioned through TIME_WAIT."""
    records = _load_state()
    violations = []
    for r in records:
        if r["state"] == "CLOSED":
            states_visited = [t["to"] for t in r.get("transition_history", [])]
            if "TIME_WAIT" not in states_visited:
                violations.append(r["conn_id"])
    assert len(violations) == 0, (
        f"CLOSED without TIME_WAIT in history: {violations}")


def test_delta_timestamps_reasonable():
    """Gateway delta connections must not have timestamps >5min from other gateways.

    After correct epoch normalization, delta events should be within a few
    seconds of the overall event window, not 25 minutes in the future.
    """
    records = _load_state()
    from datetime import datetime

    # Find timestamp range for non-delta connections
    non_delta_ts = []
    delta_ts = []
    for r in records:
        for t in r.get("transition_history", []):
            ts = t["timestamp"]
            if r["conn_id"] in ("conn_008", "conn_009"):
                delta_ts.append(ts)
            else:
                non_delta_ts.append(ts)

    if not non_delta_ts or not delta_ts:
        return

    max_non_delta = max(non_delta_ts)
    max_delta = max(delta_ts)

    nd_dt = datetime.fromisoformat(max_non_delta.replace("Z", "+00:00"))
    d_dt = datetime.fromisoformat(max_delta.replace("Z", "+00:00"))
    gap = abs((d_dt - nd_dt).total_seconds())

    assert gap < 300, (
        f"delta timestamps {gap:.0f}s from other gateways (max 300s). "
        f"Epoch normalization may be broken.")


def test_conn003_stays_established():
    """conn_003 has no close events — it must remain ESTABLISHED."""
    records = _load_state()
    for r in records:
        if r["conn_id"] == "conn_003":
            assert r["state"] == "ESTABLISHED", (
                f"conn_003 should be ESTABLISHED (no close events), got {r['state']}")
            return
    assert False, "conn_003 not found in output"


def test_export_hash_integrity():
    """SHA-256 in report must match recomputation from state file."""
    report = _load_report()
    with open(STATE_PATH) as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]
    hasher = hashlib.sha256()
    for line in lines:
        hasher.update(line.encode("utf-8"))
    assert hasher.hexdigest() == report["sha256"], "hash mismatch"


def test_slow_handshake_not_swept():
    """conn_005 has a 25-second handshake — it must NOT be swept as stale.

    The reservation timeout must accommodate the full SYN retransmission
    window (SYN_RETRY_INTERVAL * MAX_RETRIES = 30s) from the protocol spec.
    """
    records = _load_state()
    for r in records:
        if r["conn_id"] == "conn_005":
            assert r["state"] != "CLOSED" or any(
                t["to"] == "TIME_WAIT" for t in r["transition_history"]
            ), (
                f"conn_005 was incorrectly swept as stale "
                f"(25s handshake within 30s protocol window)")
            return
    assert False, "conn_005 not found"
