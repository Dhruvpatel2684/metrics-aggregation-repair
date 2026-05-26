import json
import subprocess
import os
import sys

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "environment", "runtime", "output")
RUNTIME_DIR = os.path.join(os.path.dirname(__file__), "..", "environment", "runtime")

GOLDEN_HASH_PREFIX = "0c80d25ea7eb"


def _run_resolver():
    """Run the resolver and produce output files."""
    subprocess.run(
        [sys.executable, os.path.join(RUNTIME_DIR, "run_resolver.py")],
        check=True,
        cwd=RUNTIME_DIR,
    )


def _load_report():
    with open(os.path.join(OUTPUT_DIR, "report.json")) as f:
        return json.load(f)


def _load_manifest():
    with open(os.path.join(OUTPUT_DIR, "manifest.json")) as f:
        return json.load(f)


_run_resolver()


def test_output_files_exist():
    """Verify that both output files are generated."""
    assert os.path.exists(os.path.join(OUTPUT_DIR, "report.json"))
    assert os.path.exists(os.path.join(OUTPUT_DIR, "manifest.json"))


def test_report_has_required_keys():
    """Report must contain all expected top-level keys."""
    report = _load_report()
    required = [
        "engine_id",
        "levels",
        "packages_resolved",
        "source_participation",
        "resolution",
        "integrity_hash",
    ]
    for key in required:
        assert key in report, f"Missing key: {key}"


def test_manifest_has_entries():
    """Manifest must contain at least 10 resolved entries."""
    manifest = _load_manifest()
    assert "entries" in manifest
    assert len(manifest["entries"]) >= 10


def test_entries_have_required_fields():
    """Each manifest entry must have all required fields."""
    manifest = _load_manifest()
    required_fields = ["name", "version", "level", "source", "visit_count"]
    for entry in manifest["entries"]:
        for field in required_fields:
            assert field in entry, f"Entry {entry.get('name', '?')} missing field: {field}"


def test_level_distribution_l2():
    """L2 must have exactly 7 packages - requires correct boundary."""
    report = _load_report()
    assert "level_distribution" in report
    assert report["level_distribution"].get("L2") == 7, (
        f"L2 has {report['level_distribution'].get('L2')} packages, expected 7"
    )


def test_source_participation_extended():
    """The 'extended' registry must appear in source_participation."""
    report = _load_report()
    assert "extended" in report["source_participation"], (
        f"source_participation is {report['source_participation']}, 'extended' not found"
    )


def test_phase_consistency():
    """Resolution phase_consistency must be True when phases are isolated."""
    report = _load_report()
    assert report["resolution"]["phase_consistency"] is True, (
        f"phase_consistency is {report['resolution']['phase_consistency']}"
    )


def test_topological_ordering():
    """Entries must be sorted by (level, name, visit_count)."""
    manifest = _load_manifest()
    entries = manifest["entries"]
    for i in range(len(entries) - 1):
        a, b = entries[i], entries[i + 1]
        key_a = (a["level"], a["name"], a["visit_count"])
        key_b = (b["level"], b["name"], b["visit_count"])
        assert key_a <= key_b, (
            f"Ordering violation at index {i}: {a['name']} ({key_a}) "
            f"should come before {b['name']} ({key_b})"
        )


def test_integrity_hash():
    """SHA-256 hash must match expected golden value prefix."""
    manifest = _load_manifest()
    assert manifest["metadata"]["hash"].startswith(GOLDEN_HASH_PREFIX), (
        f"Hash mismatch: got {manifest['metadata']['hash'][:16]}..."
    )


def test_full_consistency():
    """Cross-check: totals match AND level count, source count, and phase status are all correct."""
    report = _load_report()
    manifest = _load_manifest()
    total_from_dist = sum(report["level_distribution"].values())
    total_from_report = report["packages_resolved"]
    total_from_manifest = len(manifest["entries"])
    assert total_from_dist == total_from_report == total_from_manifest, (
        f"Inconsistency: dist={total_from_dist}, report={total_from_report}, "
        f"manifest={total_from_manifest}"
    )
    assert len(report["level_distribution"]) == 3, (
        f"Expected 3 levels, got {len(report['level_distribution'])}"
    )
    assert "extended" in report["source_participation"], (
        f"Missing 'extended' in sources"
    )
    assert report["resolution"]["phase_consistency"] is True, (
        f"Phase consistency check failed"
    )
