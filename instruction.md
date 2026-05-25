# Spatial Index Repair - Debugging Task

## Overview

A spatial indexing system processes geographic features from multiple data sources. The system ingests features, validates geometry types, assigns geographic sectors, builds a spatial index, performs range queries, reconciles features across processing windows, and exports a coverage report with integrity verification.

The processing stages are:
1. **Ingestion** — Loading features from source JSON files and tagging with source metadata
2. **Geometry Validation** — Filtering unsupported geometry types and computing bounding boxes
3. **Sector Assignment** — Assigning features to geographic sectors and sorting for window processing
4. **Spatial Indexing** — Building an R-tree index over feature bounding boxes
5. **Window Reconciliation** — Processing features in sector-based windows with deduplication
6. **Query Execution** — Performing range queries against the spatial index
7. **Export** — Writing feature records and coverage report with integrity hash

## Problem

The spatial indexing system is producing incorrect output. After processing all source features, the coverage report shows missing features, incorrect area values, and query result counts that do not match expected spatial coverage. The system should process all 14 raw features (from 3 sources), deduplicate shared feature IDs based on source priority, and produce 9 unique features in the final output with accurate area measurements.

## Environment

- **Language**: Python 3.11
- **Runtime files**: `/app/runtime/` (source code, config, data, output directory)
- **Config**: `/app/runtime/config/indexer.ini`
- **Source data**: `/app/runtime/data/*.json` (3 source files)
- **Output**: `/app/runtime/output/` (generated JSONL and JSON files)
- **Global system-wide tooling**: `uv` and `pytest` are available for running tests

## Task

Investigate and repair the runtime source files so that the spatial indexing system produces correct output. It is invoked via `python3 -m runtime.run_indexer` from the `/app` directory.

After repair, running the system should produce:
- 9 unique features (5 POIs deduplicated from alpha/beta + 4 gamma features)
- All three sources represented in output
- Both LineString features included from gamma source
- Correct area values (no accumulation inflation)
- Priority-based deduplication (alpha wins over beta for shared IDs)
- 14 spatial query results (all indexed features within bounds)
- Consistent integrity hash

## Output Schema

### spatial_features.jsonl

Each line is a JSON record with fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Feature identifier |
| `type` | string | Geometry type (Point, Polygon, LineString) |
| `bbox` | array | Bounding box [min_lon, min_lat, max_lon, max_lat] |
| `area_sqm` | float | Feature area in square meters |
| `source` | string | Source name (alpha, beta, gamma) |
| `sector` | integer | Assigned geographic sector ID |
| `properties` | object | Feature properties from source data |

### coverage_report.json

| Field | Type | Description |
|-------|------|-------------|
| `integrity_hash` | string | SHA-256 over sorted feature records |
| `total_features` | integer | Number of unique features exported |
| `query_result_count` | integer | Number of features matching the spatial query |
| `window_count` | integer | Number of processing windows |
| `source_distribution` | object | Feature count per source |
| `type_distribution` | object | Feature count per geometry type |
| `query_metadata` | object | Query configuration parameters |
| `feature_areas` | object | Per-feature area values |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_indexer.py` | Main entry point orchestrating all stages |
| `/app/runtime/geometry.py` | Geometry type validation and bounding box computation |
| `/app/runtime/ingest.py` | Feature loading, sector assignment, window sorting |
| `/app/runtime/rtree.py` | Spatial index with range query support |
| `/app/runtime/query_engine.py` | Configures and executes spatial queries |
| `/app/runtime/reconciler.py` | Window-based feature reconciliation and deduplication |
| `/app/runtime/export.py` | Output file writing with integrity verification |
| `/app/runtime/config/indexer.ini` | System configuration parameters |
| `/app/runtime/data/` | Source feature files (read-only data) |

## Notes

- Source data files are correct and should not be modified
- The R-tree intersection logic is correct
- Configuration file format is standard INI
- Source priority determines deduplication precedence (lower number = higher authority)
- Features may appear in multiple processing windows when their source variants map to different sectors
- Multiple interacting issues may exist across the processing stages
