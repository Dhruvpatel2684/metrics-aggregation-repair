"""Output writing and integrity hash generation for coverage reports."""

import json
import hashlib
import os


def serialize_feature_record(feature):
    """Convert an internal feature to the output record format."""
    return {
        "id": feature["id"],
        "source": feature["_source"],
        "geometry": feature["geometry"],
        "properties": feature["properties"],
        "bounds": feature.get("_bounds"),
    }


def compute_integrity_hash(records):
    """Compute SHA-256 hash over serialized feature records.

    Records are JSON-encoded with sorted keys and compact separators
    to produce a deterministic fingerprint.
    """
    content = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_coverage_report(report_path, features_path, results, query_bounds,
                          tree_stats, total_features_loaded):
    """Write the coverage report and indexed features to output files.

    The report includes query metadata, tree statistics, and an integrity
    hash computed over the result set.

    Args:
        report_path: Path for the JSON coverage report
        features_path: Path for the indexed features output
        results: List of features returned by the query
        query_bounds: The bounding box used for the query
        tree_stats: Dictionary of R-tree statistics
        total_features_loaded: Count of features processed by the pipeline
    """
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    os.makedirs(os.path.dirname(features_path), exist_ok=True)

    sorted_results = sorted(results, key=lambda f: f["id"])

    output_features = []
    for feature in sorted_results:
        output_features.append(serialize_feature_record(feature))

    unsorted_records = []
    for feature in results:
        unsorted_records.append(serialize_feature_record(feature))

    integrity_hash = compute_integrity_hash(unsorted_records)

    report = {
        "query_bounds": {
            "min_x": query_bounds[0],
            "min_y": query_bounds[1],
            "max_x": query_bounds[2],
            "max_y": query_bounds[3],
        },
        "total_features": total_features_loaded,
        "results_count": len(sorted_results),
        "tree_stats": tree_stats,
        "integrity_hash": integrity_hash,
        "sources_represented": list(set(f["source"] for f in output_features)),
    }

    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2)

    with open(features_path, "w") as fh:
        json.dump(output_features, fh, indent=2)
