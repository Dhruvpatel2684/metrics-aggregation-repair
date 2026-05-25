"""Verification tests for the spatial indexing system.

These tests validate the coverage report and indexed features output
against expected correctness criteria.
"""

import json
import hashlib
import os
import pytest


REPORT_PATH = "/app/runtime/output/coverage_report.json"
FEATURES_PATH = "/app/runtime/output/indexed_features.json"


@pytest.fixture
def report():
    """Load the coverage report."""
    assert os.path.exists(REPORT_PATH), f"Report not found at {REPORT_PATH}"
    with open(REPORT_PATH) as fh:
        return json.load(fh)


@pytest.fixture
def features():
    """Load the indexed features output."""
    assert os.path.exists(FEATURES_PATH), f"Features file not found at {FEATURES_PATH}"
    with open(FEATURES_PATH) as fh:
        return json.load(fh)


def test_output_files_exist():
    """Both output files must be present after system execution."""
    assert os.path.exists(REPORT_PATH), "Coverage report file is missing"
    assert os.path.exists(FEATURES_PATH), "Indexed features file is missing"
    assert os.path.getsize(REPORT_PATH) > 0, "Coverage report is empty"
    assert os.path.getsize(FEATURES_PATH) > 0, "Indexed features file is empty"


def test_feature_count_correct(report, features):
    """Report total_features must match the actual number of output records."""
    actual_count = len(features)
    reported_total = report["total_features"]
    assert reported_total == actual_count, (
        f"Report claims {reported_total} total features but output "
        f"contains {actual_count} records"
    )


def test_all_sources_represented(report, features):
    """Features from all three data sources must appear in results."""
    sources_in_features = set(f["source"] for f in features)
    expected_sources = {"alpha", "beta", "gamma"}
    assert expected_sources.issubset(sources_in_features), (
        f"Missing sources in output: {expected_sources - sources_in_features}. "
        f"Only found: {sources_in_features}"
    )


def test_query_results_bounded(report):
    """Query result count must be reasonable (not zero, not the entire dataset)."""
    count = report["results_count"]
    assert count >= 5, f"Too few results ({count}), expected at least 5"
    assert count <= 12, f"Too many results ({count}), expected at most 12"


def test_gamma_features_included(features):
    """At least 2 gamma-sourced features must be present in query results."""
    gamma_features = [f for f in features if f["source"] == "gamma"]
    assert len(gamma_features) >= 2, (
        f"Expected at least 2 gamma features but found {len(gamma_features)}. "
        f"Gamma polygon features may not be correctly indexed."
    )


def test_no_duplicate_features(features):
    """No duplicate feature IDs should exist in the output."""
    ids = [f["id"] for f in features]
    duplicates = [fid for fid in ids if ids.count(fid) > 1]
    assert len(duplicates) == 0, (
        f"Duplicate feature IDs found in output: {set(duplicates)}"
    )


def test_bounds_are_valid(features):
    """All feature bounds must satisfy min <= max for both axes."""
    for feature in features:
        bounds = feature.get("bounds")
        assert bounds is not None, f"Feature {feature['id']} has no bounds"
        min_x, min_y, max_x, max_y = bounds
        assert min_x <= max_x, (
            f"Feature {feature['id']} has invalid X bounds: "
            f"min_x={min_x} > max_x={max_x}"
        )
        assert min_y <= max_y, (
            f"Feature {feature['id']} has invalid Y bounds: "
            f"min_y={min_y} > max_y={max_y}"
        )


def test_integrity_hash(report, features):
    """Report integrity hash must match recomputation from sorted output features."""
    sorted_features = sorted(features, key=lambda f: f["id"])

    hashable_records = []
    for f in sorted_features:
        hashable_records.append({
            "id": f["id"],
            "source": f["source"],
            "geometry": f["geometry"],
            "properties": f["properties"],
            "bounds": f["bounds"],
        })

    content = json.dumps(hashable_records, sort_keys=True, separators=(",", ":"))
    expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    assert report["integrity_hash"] == expected_hash, (
        f"Integrity hash mismatch.\n"
        f"  Report:   {report['integrity_hash']}\n"
        f"  Computed: {expected_hash}\n"
        f"The hash must be computed over the sorted, serialized feature records."
    )
