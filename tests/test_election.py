"""Tests for the Raft election verification system.

Validates cluster health reports and committed entry manifests
produced by the election verification system.
"""

import json
import os

import pytest


OUTPUT_DIR = "/app/runtime/output"
HEALTH_PATH = os.path.join(OUTPUT_DIR, "cluster_health.json")
ENTRIES_PATH = os.path.join(OUTPUT_DIR, "committed_entries.json")


def load_health():
    with open(HEALTH_PATH) as f:
        return json.load(f)


def load_entries():
    with open(ENTRIES_PATH) as f:
        return json.load(f)


# --- EASY TESTS (pass with buggy code) ---


class TestEasy:
    def test_output_files_exist(self):
        """Verify that both output files are created."""
        assert os.path.isfile(HEALTH_PATH), "cluster_health.json not found"
        assert os.path.isfile(ENTRIES_PATH), "committed_entries.json not found"

    def test_record_count_threshold(self):
        """Verify committed entries has at least 3 entries."""
        entries = load_entries()
        assert len(entries) >= 3, "Expected at least 3 committed entries"

    def test_json_structure_valid(self):
        """Verify cluster_health.json has all required keys."""
        health = load_health()
        required_keys = [
            "cluster_id",
            "total_nodes",
            "active_voters",
            "quorum_reached",
            "leader_node",
            "election_term",
            "avg_heartbeat_ms",
            "election_timeout_ms",
            "committed_count",
        ]
        for key in required_keys:
            assert key in health, f"Missing required key: {key}"

    def test_output_directory_exists(self):
        """Verify the output directory exists."""
        assert os.path.isdir(OUTPUT_DIR), "Output directory does not exist"


# --- MEDIUM TESTS (need 1-2 bug fixes) ---


class TestMedium:
    def test_voter_count_accuracy(self):
        """Active voters must equal 4 (node1, node2, node3, node4)."""
        health = load_health()
        assert health["active_voters"] == 4, (
            f"Expected 4 active voters but got {health['active_voters']}; "
            "all nodes including node4 must be counted as valid voters"
        )

    def test_timeout_value_correctness(self):
        """Election timeout must be 150ms from strict timing configuration."""
        health = load_health()
        assert health["election_timeout_ms"] == 150, (
            f"Expected election_timeout_ms=150 but got {health['election_timeout_ms']}; "
            "timeout should come from strict timing parameters"
        )

    def test_individual_node_metrics(self):
        """Votes from node4 must be counted toward quorum."""
        health = load_health()
        assert health["quorum_reached"] is True, "Quorum must be reached"
        assert health["active_voters"] == 4, (
            "All 4 voters must be recognized for correct quorum calculation"
        )


# --- HARD TESTS (need 3-4 bug fixes) ---


class TestHard:
    def test_committed_entries_ordering(self):
        """Committed entries must be ordered by (timestamp, node_id, term)
        for deterministic cluster consensus."""
        entries = load_entries()
        for i in range(1, len(entries)):
            prev = entries[i - 1]
            curr = entries[i]
            prev_key = (prev["timestamp"], prev["node_id"], prev["term"])
            curr_key = (curr["timestamp"], curr["node_id"], curr["term"])
            assert prev_key <= curr_key, (
                f"entries must be ordered by (timestamp, node_id, term) "
                f"for deterministic cluster consensus: "
                f"entry at position {i-1} {prev_key} should come before "
                f"entry at position {i} {curr_key}"
            )

    def test_full_health_report_accuracy(self):
        """All health report values must be correct after full repair."""
        health = load_health()
        assert health["active_voters"] == 4, (
            f"active_voters should be 4, got {health['active_voters']}"
        )
        assert health["election_timeout_ms"] == 150, (
            f"election_timeout_ms should be 150, got {health['election_timeout_ms']}"
        )
        assert health["committed_count"] == 12, (
            f"committed_count should be 12, got {health['committed_count']}"
        )
        assert health["quorum_reached"] is True, "quorum_reached should be True"
        assert health["cluster_id"] == "raft-cluster-7"
        assert health["total_nodes"] == 4
        assert health["leader_node"] == "node_alpha"
        assert health["election_term"] == 6

    def test_window_aggregation_values(self):
        """Window ack_count values must reflect per-window totals,
        not cumulative totals across windows."""
        entries = load_entries()
        ack_values = [e["ack_count"] for e in entries]
        max_ack = max(ack_values)
        assert max_ack <= 60, (
            f"Maximum ack_count is {max_ack} which exceeds per-window maximum; "
            "window aggregation should reflect per-window values, "
            "not cumulative totals"
        )
