"""Validation suite for Raft election reconciliation system."""

import hashlib
import json
import os

import pytest


OUTPUT_DIR = "/app/runtime/output"
STATE_FILE = os.path.join(OUTPUT_DIR, "reconciliation_state.json")
MANIFEST_FILE = os.path.join(OUTPUT_DIR, "commitment_manifest.json")


def load_state():
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def load_manifest():
    with open(MANIFEST_FILE, "r") as f:
        return json.load(f)


class TestEasy:
    """Basic structural validation - should always pass."""

    def test_output_files_exist(self):
        assert os.path.isfile(STATE_FILE), "reconciliation state output not found"
        assert os.path.isfile(MANIFEST_FILE), "commitment manifest output not found"

    def test_reconciliation_state_structure(self):
        state = load_state()
        required_keys = [
            "cluster_id", "total_nodes", "active_voters",
            "quorum_reached", "quorum_size", "leader_node",
            "current_epoch", "epoch_stats", "reconciliation",
            "integrity_hash",
        ]
        for key in required_keys:
            assert key in state, f"missing required key in reconciliation state"

    def test_manifest_has_entries(self):
        manifest = load_manifest()
        assert "entries" in manifest, "manifest missing entries field"
        assert len(manifest["entries"]) >= 5, "insufficient entries in commitment manifest"

    def test_manifest_entry_fields(self):
        manifest = load_manifest()
        required_fields = ["index", "ts", "nid", "op", "phase", "term"]
        for entry in manifest["entries"]:
            for field in required_fields:
                assert field in entry, "manifest entry missing required field"


class TestMedium:
    """Reconciliation validation - requires partial bug fixes."""

    def test_epoch_record_distribution(self):
        state = load_state()
        epoch_stats = state["epoch_stats"]
        assert "5" in epoch_stats, "epoch 5 not present in stats"
        count = epoch_stats["5"]["record_count"]
        assert count == 15, "epoch record distribution does not match expected reconciliation state"

    def test_voter_participation(self):
        state = load_state()
        active = state["active_voters"]
        assert active == 4, "voter participation does not match cluster configuration"

    def test_propose_phase_totals(self):
        state = load_state()
        propose = state["reconciliation"]["propose"]
        assert propose["windows_processed"] == 10, "propose phase aggregation diverges from expected reconciliation state"


class TestHard:
    """Full system validation - requires all bug fixes."""

    def test_manifest_integrity_hash(self):
        """Manifest entries must be ordered by (ts, nid, term) and the
        computed hash must match the stored manifest_hash field."""
        manifest = load_manifest()
        entries = manifest["entries"]
        canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
        computed_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        assert computed_hash == manifest.get("manifest_hash"), (
            "commitment manifest integrity check failed - "
            "the manifest_hash field does not match the computed hash of entries; "
            "check sort order in merger module (canonical order is ts, nid, term)"
        )
        for i in range(1, len(entries)):
            prev = entries[i - 1]
            curr = entries[i]
            prev_key = (prev["ts"], prev["nid"], prev["term"])
            curr_key = (curr["ts"], curr["nid"], curr["term"])
            assert prev_key <= curr_key, (
                f"manifest entries not in canonical order at position {i}: "
                f"{prev_key} should precede {curr_key} "
                f"(expected sort: ts, nid, term)"
            )

    def test_reconciliation_state_integrity(self):
        state = load_state()
        to_hash = {k: v for k, v in state.items() if k != "integrity_hash"}
        canonical = json.dumps(to_hash, sort_keys=True, separators=(",", ":"))
        computed = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        assert computed == state["integrity_hash"], "reconciliation state diverges from expected deterministic output"
        assert computed == "14b9eb341ff855f5", "reconciliation state diverges from expected deterministic output"

    def test_quorum_consistency(self):
        state = load_state()
        assert state["quorum_reached"] is True, "quorum validation inconsistency detected"
        assert state["quorum_size"] == 3, "quorum validation inconsistency detected"
        assert state["active_voters"] == 4, "quorum validation inconsistency detected"
