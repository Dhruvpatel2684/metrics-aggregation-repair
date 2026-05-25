"""Main entry point for the spatial indexing pipeline.

Orchestrates the full workflow:
1. Load configuration
2. Ingest features from all data sources
3. Deduplicate features across sources
4. Compute bounding boxes for each feature
5. Build the R-tree spatial index
6. Execute range queries
7. Export coverage report with integrity hash
"""

import configparser
import sys
import os

sys.path.insert(0, "/app")

from runtime.ingest import load_all_sources, deduplicate_features
from runtime.geometry import compute_feature_bounds
from runtime.rtree import SpatialIndex
from runtime.query_engine import QueryEngine
from runtime.export import write_coverage_report


def main():
    config_path = "/app/runtime/config/indexer.ini"

    config = configparser.ConfigParser()
    config.read(config_path)

    data_directory = config.get("sources", "data_directory")
    file_pattern = config.get("sources", "file_pattern")
    node_capacity = config.getint("indexing", "node_capacity")
    split_min = config.getint("indexing", "split_min_entries")
    report_path = config.get("output", "report_path")
    features_path = config.get("output", "features_path")

    print(f"[indexer] Loading sources from {data_directory}")
    all_features = load_all_sources(data_directory, file_pattern)
    total_loaded = len(all_features)
    print(f"[indexer] Loaded {total_loaded} features from all sources")

    if config.getboolean("dedup", "enabled"):
        features = deduplicate_features(all_features)
        print(f"[indexer] After deduplication: {len(features)} unique features")
    else:
        features = all_features

    print("[indexer] Computing feature bounds")
    for feature in features:
        bounds = compute_feature_bounds(feature)
        feature["_bounds"] = bounds

    print(f"[indexer] Building spatial index (capacity={node_capacity})")
    index = SpatialIndex(node_capacity=node_capacity, split_min=split_min)
    for feature in features:
        index.insert(feature, feature["_bounds"])

    print("[indexer] Executing range query")
    engine = QueryEngine(config_path)
    results, query_bounds = engine.execute(index)
    print(f"[indexer] Query returned {len(results)} results")

    tree_stats = index.get_stats()

    write_coverage_report(
        report_path=report_path,
        features_path=features_path,
        results=results,
        query_bounds=query_bounds,
        tree_stats=tree_stats,
        total_features_loaded=total_loaded,
    )
    print(f"[indexer] Report written to {report_path}")
    print(f"[indexer] Features written to {features_path}")
    print("[indexer] Pipeline complete")


if __name__ == "__main__":
    main()
