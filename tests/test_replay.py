"""Test suite for the event replay engine output validation."""

import hashlib
import json
import os

import pytest


OUTPUT_DIR = "/app/runtime/output"
VIEWS_FILE = os.path.join(OUTPUT_DIR, "account_views.json")
REPORT_FILE = os.path.join(OUTPUT_DIR, "replay_report.json")

EXPECTED_BALANCES = {
    "acct_001": 1500,
    "acct_002": 2300,
    "acct_003": 800,
    "acct_004": 3100,
    "acct_005": 1900,
}


@pytest.fixture
def account_views():
    with open(VIEWS_FILE, "r") as f:
        return json.load(f)


@pytest.fixture
def replay_report():
    with open(REPORT_FILE, "r") as f:
        return json.load(f)


class TestEasyChecks:
    """Basic structural checks that pass regardless of bug state."""

    def test_output_files_exist(self):
        """Both output files must be present after replay."""
        assert os.path.exists(VIEWS_FILE), (
            f"Missing output file: {VIEWS_FILE}"
        )
        assert os.path.exists(REPORT_FILE), (
            f"Missing output file: {REPORT_FILE}"
        )

    def test_all_accounts_present(self, account_views):
        """All 5 accounts must appear in the materialized view."""
        accounts = account_views["accounts"]
        expected_ids = {"acct_001", "acct_002", "acct_003", "acct_004", "acct_005"}
        assert set(accounts.keys()) == expected_ids, (
            f"Expected accounts {expected_ids}, got {set(accounts.keys())}"
        )

    def test_report_structure(self, replay_report):
        """Replay report must contain all required fields."""
        required_fields = [
            "total_events_loaded",
            "events_by_type",
            "events_by_stream",
            "batch_count",
            "final_balances",
            "compaction_applied",
            "compaction_threshold",
            "integrity_hash",
        ]
        for field in required_fields:
            assert field in replay_report, (
                f"Missing required field '{field}' in replay_report.json"
            )

    def test_total_events_loaded(self, replay_report):
        """Report must show 50 total events loaded from all streams."""
        assert replay_report["total_events_loaded"] == 50, (
            f"Expected 50 total events, got {replay_report['total_events_loaded']}. "
            f"Check that all stream files in /app/runtime/streams/ are being loaded."
        )


class TestMediumChecks:
    """Checks that require fixing one or two specific defects."""

    def test_snapshot_events_applied(self, account_views):
        """Snapshot events must be tracked and applied (5 total across streams).

        Both accounts.jsonl and system.jsonl contain snapshot_taken events.
        All must be included in processing. Check tracked_types configuration
        in /app/runtime/config/replay.ini and the parsing logic in
        /app/runtime/projector.py.
        """
        metadata = account_views["metadata"]
        assert metadata["snapshot_events_applied"] == 5, (
            f"Expected 5 snapshot events applied, got {metadata['snapshot_events_applied']}. "
            f"Verify that 'snapshot_taken' is correctly parsed from tracked_types in "
            f"/app/runtime/projector.py"
        )

    def test_no_inflated_balances(self, account_views):
        """No account balance should exceed 5000 (indicates accumulation error).

        If balances are inflated, check how batch processing accumulates values
        in /app/runtime/reducer.py. The batch fold operation should produce the
        final value, not accumulate across batches.
        """
        accounts = account_views["accounts"]
        for acct, data in accounts.items():
            assert data["balance"] <= 5000, (
                f"Account {acct} has inflated balance {data['balance']}. "
                f"Check batch accumulation logic in /app/runtime/reducer.py"
            )

    def test_acct_003_balance(self, account_views):
        """Account acct_003 must have exact balance of 800.

        This account has events from multiple streams at the same timestamp.
        Check event ordering in /app/runtime/event_store.py to ensure
        deterministic sort when timestamps collide across streams.
        """
        balance = account_views["accounts"]["acct_003"]["balance"]
        assert balance == 800, (
            f"acct_003 balance is {balance}, expected 800. "
            f"Check event ordering in /app/runtime/event_store.py — "
            f"events from different streams sharing a timestamp need "
            f"deterministic ordering by stream origin."
        )


class TestHardChecks:
    """Checks requiring multiple fixes working together."""

    def test_exact_balances(self, account_views):
        """All account balances must match expected values exactly.

        Expected: acct_001=1500, acct_002=2300, acct_003=800,
        acct_004=3100, acct_005=1900.

        These values come from snapshot_taken events which authoritatively
        reset account balances. Multiple stages must work correctly:
        event ordering, type filtering, and balance computation.
        """
        accounts = account_views["accounts"]
        for acct, expected in EXPECTED_BALANCES.items():
            actual = accounts[acct]["balance"]
            assert actual == expected, (
                f"Balance mismatch for {acct}: got {actual}, expected {expected}. "
                f"Snapshot events should reset balances authoritatively."
            )

    def test_compaction_config(self, account_views):
        """Compaction must use aggressive threshold (10) with 5 compactions.

        The materializer should read from [compaction.aggressive] section
        which specifies threshold_events=10 for materialized view rebuilds.
        Check /app/runtime/materializer.py config section reference.
        """
        metadata = account_views["metadata"]
        assert metadata["compaction_threshold"] == 10, (
            f"Compaction threshold is {metadata['compaction_threshold']}, expected 10. "
            f"The materializer should use [compaction.aggressive] section from "
            f"/app/runtime/config/replay.ini"
        )
        assert metadata["compactions_performed"] == 5, (
            f"Compactions performed is {metadata['compactions_performed']}, expected 5. "
            f"With threshold=10 and correct event counts, all 5 accounts should compact."
        )

    def test_integrity_hash(self, replay_report):
        """Integrity hash must match recomputation from correct final state.

        This validates that all balances are correct AND the hash computation
        is deterministic. Requires all processing stages to produce correct output.
        """
        expected_content = json.dumps({
            "balances": {k: v for k, v in sorted(EXPECTED_BALANCES.items())},
            "total_events": 50
        }, sort_keys=True)
        expected_hash = hashlib.sha256(expected_content.encode()).hexdigest()

        assert replay_report["integrity_hash"] == expected_hash, (
            f"Integrity hash mismatch. Got {replay_report['integrity_hash'][:16]}..., "
            f"expected {expected_hash[:16]}... "
            f"All processing stages must produce correct output for hash to match."
        )
