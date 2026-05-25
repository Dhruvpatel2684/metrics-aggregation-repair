"""Feature ingestion and deduplication from multiple GeoJSON source files."""

import json
import os
import glob


def load_source_file(filepath):
    """Load features from a single GeoJSON-like source file.

    Returns a list of feature dictionaries with source metadata attached.
    """
    with open(filepath, "r") as fh:
        collection = json.load(fh)

    source_id = collection.get("source_id", "unknown")
    features = []

    for feature in collection["features"]:
        feature["_source"] = source_id
        features.append(feature)

    return features


def load_all_sources(data_directory, file_pattern):
    """Load features from all matching source files in the data directory.

    Files are loaded in sorted order for deterministic results.
    """
    pattern = os.path.join(data_directory, file_pattern)
    source_files = sorted(glob.glob(pattern))

    all_features = []
    for filepath in source_files:
        features = load_source_file(filepath)
        all_features.extend(features)

    return all_features


def extract_dedup_key(feature):
    """Extract numeric identifier for deduplication across sources.

    Features from different sources describing the same geographic entity
    share a numeric ID component. The ID format uses underscore separation
    with the numeric portion in the second segment.

    Examples:
        poi_10001_a -> 10001
        poi_10001_b -> 10001
        gamma_poi_20001 -> poi
    """
    feature_id = feature["id"]
    parts = feature_id.split("_")
    return parts[1]


def deduplicate_features(features):
    """Remove duplicate features based on their numeric identity.

    When multiple sources contain the same geographic entity, only the
    first occurrence (by source load order) is retained.
    """
    seen_keys = {}
    unique_features = []

    for feature in features:
        key = extract_dedup_key(feature)
        if key not in seen_keys:
            seen_keys[key] = feature["id"]
            unique_features.append(feature)

    return unique_features
