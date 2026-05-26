"""Validation suite for dependency graph resolution engine."""
import hashlib
import json
import os

import pytest

REPORT_PATH = "/app/runtime/output/resolution_report.json"
MANIFEST_PATH = "/app/runtime/output/install_manifest.json"


def load_report():
    with open(REPORT_PATH) as f:
        return json.load(f)


def load_manifest():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


class TestStructural:
    """Basic structural validation - always passes."""

    def test_output_files_exist(self):
        """Verify both output files are generated."""
        assert os.path.isfile(REPORT_PATH), "resolution report not found"
        assert os.path.isfile(MANIFEST_PATH), "install manifest not found"

    def test_report_required_keys(self):
        """Verify report contains all required fields."""
        report = load_report()
        required = [
            "engine_id", "strategy", "ancestor_threshold",
            "active_sources", "packages_available", "packages_resolved",
            "install_order_length", "scoring", "integrity_hash",
        ]
        for key in required:
            assert key in report, f"missing field: {key}"

    def test_manifest_structure(self):
        """Verify manifest has install_order with entries."""
        manifest = load_manifest()
        assert "install_order" in manifest
        assert "manifest_hash" in manifest
        assert len(manifest["install_order"]) >= 8

    def test_install_entry_fields(self):
        """Verify each entry has required fields."""
        manifest = load_manifest()
        fields = ["name", "version", "source", "depth", "dep_count"]
        for entry in manifest["install_order"]:
            for f in fields:
                assert f in entry, f"entry missing field: {f}"


class TestSemantic:
    """Semantic validation requiring partial fixes."""

    def test_active_source_count(self):
        """All configured sources must be active."""
        report = load_report()
        assert report["active_sources"] == 3, (
            "source registry count diverges from expected configuration"
        )

    def test_ancestor_threshold(self):
        """Traversal threshold must use bounded configuration."""
        report = load_report()
        assert report["ancestor_threshold"] == 3, (
            "ancestor threshold does not match bounded traversal parameters"
        )

    def test_scoring_total_resolved(self):
        """All resolved packages must be scored independently."""
        report = load_report()
        assert report["scoring"]["total_resolved"] == 18, (
            "scoring total diverges from resolution count"
        )


class TestConsistency:
    """Cross-concern consistency requiring all fixes."""

    def test_install_order_deterministic(self):
        """Install order must follow (depth desc, name asc, version asc).

        Packages at the same depth must be ordered by name then version
        to ensure deterministic installation plans.
        """
        manifest = load_manifest()
        items = manifest["install_order"]
        for i in range(len(items) - 1):
            curr = items[i]
            nxt = items[i + 1]
            curr_key = (-curr["depth"], curr["name"], curr["version"])
            nxt_key = (-nxt["depth"], nxt["name"], nxt["version"])
            assert curr_key <= nxt_key, (
                f"install order not deterministic at position {i}: "
                f"({curr['name']}, depth={curr['depth']}) before "
                f"({nxt['name']}, depth={nxt['depth']}); "
                f"expected ordering: depth descending, then name, then version"
            )

    def test_integrity_hash(self):
        """Report integrity hash must match computed canonical state."""
        report = load_report()
        hashable = {k: v for k, v in report.items() if k != "integrity_hash"}
        canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
        computed = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        assert computed == report["integrity_hash"], (
            "integrity hash does not match report state"
        )
        assert computed == "33a7a2b85ee404c3", (
            "resolution state diverges from expected canonical output"
        )

    def test_full_consistency(self):
        """Cross-concern validation across all subsystems."""
        report = load_report()
        scoring = report["scoring"]
        assert report["active_sources"] == 3
        assert report["ancestor_threshold"] == 3
        assert "internal" in scoring["source_scores"], (
            "internal source missing from scoring"
        )
        assert scoring["source_scores"]["internal"]["packages"] == 5
        assert scoring["source_scores"]["community"]["packages"] == 6
        assert scoring["source_scores"]["core"]["packages"] == 7
        assert report["packages_resolved"] == 18
