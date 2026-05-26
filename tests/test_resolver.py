"""
Validation tests for the dependency resolution system.

Tests are ordered by difficulty:
- Easy (1-4): Structure and basic output validation
- Medium (5-7): Semantic correctness checks
- Hard (8-10): Cross-concern integrity verification
"""

import json
import os
import subprocess
import sys

import pytest


REPORT_PATH = "/app/runtime/output/resolution_report.json"
MANIFEST_PATH = "/app/runtime/output/install_manifest.json"


@pytest.fixture(scope="session", autouse=True)
def run_resolver():
    """Execute the resolver before running tests."""
    result = subprocess.run(
        [sys.executable, "-m", "runtime.run_resolver"],
        cwd="/app",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}", file=sys.stderr)
    yield result


class TestEasyStructure:
    """Basic structural validation - always passes if system runs."""

    def test_output_files_exist(self):
        """Both output files must be written."""
        assert os.path.isfile(REPORT_PATH), (
            f"Resolution report not found at {REPORT_PATH}")
        assert os.path.isfile(MANIFEST_PATH), (
            f"Installation manifest not found at {MANIFEST_PATH}")

    def test_report_structure(self):
        """Report must contain required top-level sections."""
        with open(REPORT_PATH) as f:
            report = json.load(f)
        assert "metadata" in report
        assert "scores" in report
        meta = report["metadata"]
        required_fields = [
            "total_packages", "source_count", "registries_processed",
            "removed_cycles", "max_depth", "scoring_passes",
            "integrity_hash"
        ]
        for field in required_fields:
            assert field in meta, f"Missing metadata field: {field}"

    def test_manifest_structure(self):
        """Manifest must contain required sections."""
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        assert "install_order" in manifest
        assert "total_install_count" in manifest
        assert "integrity_hash" in manifest
        assert isinstance(manifest["install_order"], list)
        assert len(manifest["install_order"]) > 0

    def test_install_entry_fields(self):
        """Each install entry must have required fields."""
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        required = {"name", "version", "source", "depth", "score"}
        for entry in manifest["install_order"]:
            missing = required - set(entry.keys())
            assert not missing, (
                f"Entry {entry.get('name', '?')} missing fields: {missing}")


class TestMediumSemantics:
    """Semantic correctness - validates resolution logic."""

    def test_source_registry_count(self):
        """Resolution must process exactly 3 active registries."""
        with open(REPORT_PATH) as f:
            report = json.load(f)
        registries = report["metadata"]["registries_processed"]
        assert len(registries) == 3, (
            f"Expected 3 active registries, got {len(registries)}: {registries}. "
            f"Only alias-verified sources should pass the filter.")

    def test_package_resolution_count(self):
        """Resolved package count must match filtered input."""
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        count = manifest["total_install_count"]
        assert count == 35, (
            f"Expected 35 resolved packages, got {count}. "
            f"Check source filtering for unverified registry leakage.")

    def test_scoring_pass_count(self):
        """Scorer must execute exactly one pass per active registry."""
        with open(REPORT_PATH) as f:
            report = json.load(f)
        passes = report["metadata"]["scoring_passes"]
        assert passes == 3, (
            f"Expected 3 scoring passes (one per registry), got {passes}. "
            f"Non-active sources should not trigger scoring passes.")


class TestHardIntegrity:
    """Cross-concern integrity - requires all components correct."""

    def test_installation_order_determinism(self):
        """
        Install order must be deterministic: sorted by descending depth,
        then ascending package name, then ascending version.
        """
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        order = manifest["install_order"]
        for i in range(len(order) - 1):
            curr = order[i]
            nxt = order[i + 1]
            curr_key = (-curr["depth"], curr["name"], curr["version"])
            nxt_key = (-nxt["depth"], nxt["name"], nxt["version"])
            assert curr_key <= nxt_key, (
                f"Installation order violation at position {i}: "
                f"{curr['name']}@{curr['version']} (depth={curr['depth']}) "
                f"must come before "
                f"{nxt['name']}@{nxt['version']} (depth={nxt['depth']}). "
                f"Correct ordering uses descending depth, then ascending "
                f"package name, then ascending version as tiebreakers.")

    def test_cycle_detection_accuracy(self):
        """No legitimate dependency edges should be flagged as cycles."""
        with open(REPORT_PATH) as f:
            report = json.load(f)
        removed = report["metadata"]["removed_cycles"]
        assert len(removed) == 0, (
            f"Found {len(removed)} incorrectly removed edge(s): {removed}. "
            f"The dependency graph contains no actual cycles. "
            f"Check the back-edge boundary comparison logic.")

    def test_integrity_hash_consistency(self):
        """
        System-wide integrity hash must match expected value.
        This validates that all resolution components produce
        correct output simultaneously.
        """
        with open(REPORT_PATH) as f:
            report = json.load(f)
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        expected = "2f75e45807987551274aafd77bbf1e754593927d64051487da10183e6cccea37"
        report_hash = report["metadata"]["integrity_hash"]
        manifest_hash = manifest["integrity_hash"]
        assert report_hash == manifest_hash, (
            "Report and manifest integrity hashes do not match.")
        assert report_hash == expected, (
            f"Integrity hash mismatch. "
            f"Got:      {report_hash}\n"
            f"Expected: {expected}\n"
            f"This indicates one or more resolution components "
            f"produce incorrect intermediate results.")
