"""
Main entry point for the spatial indexing system.
Orchestrates feature ingestion, geometry processing, spatial indexing,
range queries, window reconciliation, and report export.
"""

import configparser
import os
import sys


def load_config():
    """Load the indexer configuration from the standard path."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config", "indexer.ini")
    config.read(config_path)
    return config


def main():
    """Run the complete spatial indexing workflow."""
    config = load_config()

    # Stage 1: Ingest features from all source files
    from runtime.ingest import FeatureIngestor
    ingestor = FeatureIngestor(config)
    raw_features = ingestor.load_all_sources()

    # Stage 2: Geometry validation and bounding box computation
    from runtime.geometry import GeometryProcessor
    geom_processor = GeometryProcessor(config)

    processed_features = []
    for feature in raw_features:
        result = geom_processor.process_feature(feature)
        if result is not None:
            # Carry over internal metadata
            result["_source"] = feature["_source"]
            result["_source_priority"] = feature["_source_priority"]
            processed_features.append(result)

    # Stage 3: Sector assignment and window sorting
    processed_features = ingestor.assign_sectors(processed_features)
    sorted_features = ingestor.sort_into_windows(processed_features)

    # Stage 4: Build spatial index
    from runtime.rtree import SpatialIndex
    spatial_index = SpatialIndex()
    for feature in sorted_features:
        spatial_index.insert(feature["id"], feature["bbox"], feature)

    # Stage 5: Window reconciliation
    from runtime.reconciler import WindowReconciler
    reconciler = WindowReconciler(config)
    reconciled_features, window_count = reconciler.process_windows(sorted_features)

    # Stage 6: Execute spatial query
    from runtime.query_engine import QueryEngine
    query_engine = QueryEngine(config, spatial_index)
    query_results = query_engine.execute_query()
    query_meta = query_engine.get_query_metadata()

    # Stage 7: Export results
    from runtime.export import ReportExporter
    exporter = ReportExporter(config)
    exported_features = exporter.export_features(reconciled_features)
    report = exporter.export_report(
        reconciled_features, query_results, window_count, query_meta
    )

    print(f"Indexing complete: {len(reconciled_features)} features processed")
    print(f"Query returned {len(query_results)} results from {spatial_index.size()} indexed")
    print(f"Windows processed: {window_count}")
    print(f"Report written to {config.get('export', 'output_directory')}")


if __name__ == "__main__":
    main()
