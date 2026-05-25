"""
Tests for the spatial indexing system.
Validates that the indexer correctly processes all source features,
applies spatial queries, and produces consistent coverage reports.
"""

import json
import os

OUTPUT_DIR = "/app/runtime/output"
FEATURES_PATH = os.path.join(OUTPUT_DIR, "spatial_features.jsonl")
REPORT_PATH = os.path.join(OUTPUT_DIR, "coverage_report.json")


def load_features():
    """Load feature records from the output JSONL file."""
    features = []
    with open(FEATURES_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            features.append(json.loads(line))
    return features


def load_report():
    """Load the coverage report JSON."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


def test_output_files_exist():
    """
    Verify that the indexer produces both expected output files.
    The spatial features JSONL and coverage report must exist.
    """
    assert os.path.isfile(FEATURES_PATH), (
        f"Features file not found at {FEATURES_PATH}"
    )
    assert os.path.isfile(REPORT_PATH), (
        f"Coverage report not found at {REPORT_PATH}"
    )


def test_feature_count():
    """
    The system should produce exactly 9 unique features after deduplication.
    Source alpha and beta share feature IDs (poi_10001 through poi_10005),
    which deduplicate to 5 unique POIs. Combined with 4 gamma features
    (2 Polygons + 2 LineStrings), the total should be 9.
    """
    features = load_features()
    report = load_report()

    assert len(features) == 9, (
        f"Expected 9 features after deduplication, got {len(features)}"
    )
    assert report["total_features"] == 9, (
        f"Report total_features should be 9, got {report['total_features']}"
    )


def test_all_sources_represented():
    """
    All three data sources must be represented in the output.
    Alpha contributes high-priority POIs, beta contributes one boundary POI,
    and gamma contributes polygon and line features.
    """
    features = load_features()
    sources = set(f["source"] for f in features)

    assert "alpha" in sources, "Alpha source not represented in output"
    assert "beta" in sources, "Beta source not represented in output"
    assert "gamma" in sources, "Gamma source not represented in output"

    # Verify source distribution counts
    source_counts = {}
    for f in features:
        src = f["source"]
        source_counts[src] = source_counts.get(src, 0) + 1

    assert source_counts.get("alpha", 0) == 4, (
        f"Expected 4 features from alpha (priority dedup), got {source_counts.get('alpha', 0)}"
    )
    assert source_counts.get("gamma", 0) == 4, (
        f"Expected 4 features from gamma, got {source_counts.get('gamma', 0)}"
    )


def test_linestring_features_present():
    """
    The geometry processor should include LineString features from gamma.
    Both geo_20003 and geo_20004 are LineString type and must pass the
    supported-type filter to appear in the output.
    """
    features = load_features()
    linestrings = [f for f in features if f["type"] == "LineString"]

    assert len(linestrings) == 2, (
        f"Expected 2 LineString features, got {len(linestrings)}"
    )

    ls_ids = sorted(f["id"] for f in linestrings)
    assert ls_ids == ["geo_20003", "geo_20004"], (
        f"Expected LineString IDs ['geo_20003', 'geo_20004'], got {ls_ids}"
    )


def test_query_results_bounded():
    """
    The spatial query should return all indexed features within the
    configured range. With the correct precision tolerance, all 14
    indexed features (before deduplication) should intersect the
    query bounds.
    """
    report = load_report()
    query_count = report["query_result_count"]

    assert query_count == 14, (
        f"Expected 14 query results (all indexed features within bounds), "
        f"got {query_count}"
    )


def test_no_inflated_areas():
    """
    Point features should retain their original area values from source data.
    No feature should have an area that exceeds its source value, which would
    indicate incorrect accumulation across processing windows.
    The maximum legitimate area for a Point feature is 85.0 sqm.
    """
    features = load_features()

    point_features = [f for f in features if f["type"] == "Point"]
    for pf in point_features:
        assert pf["area_sqm"] <= 100.0, (
            f"Feature {pf['id']} has inflated area {pf['area_sqm']} "
            f"(expected <= 100.0 for point features)"
        )

    # Specifically check poi_10005 which spans two sectors
    poi_10005 = next((f for f in features if f["id"] == "poi_10005"), None)
    assert poi_10005 is not None, "poi_10005 not found in output"
    assert poi_10005["area_sqm"] == 85.0, (
        f"poi_10005 should have area 85.0, got {poi_10005['area_sqm']} "
        f"(possible accumulation error across sector windows)"
    )


def test_deterministic_source_priority():
    """
    When features share the same ID across sources, the highest-priority
    source (lowest priority number) should win via last-write-wins
    deduplication after priority-based sorting.
    Alpha (priority 1) should take precedence over beta (priority 2)
    for shared features poi_10001 through poi_10004.
    """
    features = load_features()
    feature_map = {f["id"]: f for f in features}

    # Alpha should win for shared features (higher authority = priority 1)
    for fid in ["poi_10001", "poi_10002", "poi_10003", "poi_10004"]:
        assert fid in feature_map, f"{fid} not found in output"
        assert feature_map[fid]["source"] == "alpha", (
            f"{fid} should be from alpha (priority 1), "
            f"got source '{feature_map[fid]['source']}'"
        )

    # poi_10005 is special: alpha and beta are in different sectors,
    # so beta (processed in later sector window) wins via last-write
    assert feature_map["poi_10005"]["source"] == "beta", (
        f"poi_10005 should be from beta (later sector window), "
        f"got source '{feature_map['poi_10005']['source']}'"
    )


def test_output_sorted_by_id():
    """
    The output features file should be sorted by feature ID for
    deterministic verification and reproducible hash computation.
    """
    features = load_features()
    ids = [f["id"] for f in features]
    assert ids == sorted(ids), (
        f"Features not sorted by ID. Got order: {ids}"
    )


def test_integrity_hash_consistency():
    """
    The integrity hash in the coverage report must match the expected value
    computed from correctly processed feature data. This validates that
    all features have correct types, areas, and deduplication outcomes.
    The expected hash corresponds to the 9 correctly-processed features
    with proper area values and source priority resolution.
    """
    report = load_report()

    # Expected hash for correct output: 9 features with proper deduplication,
    # area values, and geometry type inclusion
    expected_hash = "9a361f891a3489fa9fb1cdf540a973873ac87eb3d65a50b40a6f87949fe7a11c"
    actual_hash = report["integrity_hash"]

    assert actual_hash == expected_hash, (
        f"Integrity hash mismatch: report has {actual_hash}, "
        f"expected {expected_hash}. This indicates feature data "
        f"discrepancies in types, areas, or deduplication."
    )
