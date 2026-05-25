# Spatial Index Repair Task

## Overview

You are debugging a spatial indexing system that processes geographic features from multiple GeoJSON-like data sources, builds an R-tree spatial index, executes range queries, and produces a coverage report. The system is currently producing incorrect output.

## System Architecture

The system runs as a Python module invoked via:

```
cd /app
python3 -m runtime.run_indexer
```

### Processing Stages

1. **Ingestion** (`/app/runtime/ingest.py`): Loads feature collections from JSON source files in `/app/runtime/data/`. Features are loaded from `source_alpha.json`, `source_beta.json`, and `source_gamma.json`.

2. **Deduplication** (`/app/runtime/ingest.py`): Features describing the same geographic entity across different sources are deduplicated using their numeric ID component.

3. **Geometry Processing** (`/app/runtime/geometry.py`): Computes axis-aligned bounding boxes for each feature. Points use their coordinates directly; polygons use the extent of their outer ring.

4. **Spatial Indexing** (`/app/runtime/rtree.py`): Builds a simplified R-tree from the feature bounding boxes for efficient spatial querying.

5. **Range Query** (`/app/runtime/query_engine.py`): Executes a bounding-box range query centered on a configured point with a specified search radius.

6. **Export** (`/app/runtime/export.py`): Writes the query results and a coverage report with tree statistics and an integrity hash.

### Configuration

All parameters are defined in `/app/runtime/config/indexer.ini`:

- **[sources]**: Data directory path and file glob pattern
- **[indexing]**: R-tree node capacity and split parameters
- **[query]**: Query center coordinates and search radius in degrees
- **[output]**: Output file paths for report and features
- **[dedup]**: Deduplication toggle and strategy

### Data Sources

| Source | Features | Geometry Type | ID Format |
|--------|----------|---------------|-----------|
| source_alpha.json | 5 | Point | `poi_NNNNN_a` |
| source_beta.json | 5 | Point | `poi_NNNNN_b` |
| source_gamma.json | 4 | Polygon | `gamma_poi_NNNNN` |

Features from alpha and beta may share the same numeric ID (indicating the same geographic entity reported by different sources). Gamma features have unique numeric IDs.

### Output Schema

**Coverage Report** (`/app/runtime/output/coverage_report.json`):

```json
{
  "query_bounds": {"min_x": ..., "min_y": ..., "max_x": ..., "max_y": ...},
  "total_features": <number of features in output>,
  "results_count": <number of query results>,
  "tree_stats": {"total_indexed": ..., "tree_depth": ..., "node_count": ...},
  "integrity_hash": "<sha256 hex digest>",
  "sources_represented": ["alpha", "beta", "gamma"]
}
```

**Indexed Features** (`/app/runtime/output/indexed_features.json`):

```json
[
  {
    "id": "...",
    "source": "...",
    "geometry": {...},
    "properties": {...},
    "bounds": [min_x, min_y, max_x, max_y]
  }
]
```

The `total_features` field must equal the actual number of records in the indexed features file. The `integrity_hash` is computed over the sorted feature records.

## Observed Symptoms

When running the system, the following issues are present:

- The feature count reported does not match the actual output
- Gamma source features are missing or underrepresented in query results
- The query appears to cover a much larger area than intended
- The integrity hash does not match recomputation from the output file
- Polygon features from gamma are not found by range queries with correct parameters

## Environment

- **Global system-wide tooling**: `uv` and `pytest` are pre-installed and available

- **Runtime**: Python 3.11
- **Testing**: `uv run --with pytest pytest /tests/test_spatial.py -v`
- **Working directory**: `/app`
- **All paths are absolute** within the container environment

## Testing

Run the verification suite:

```bash
cd /app
python3 -m runtime.run_indexer
uv run --with pytest pytest /tests/test_spatial.py -v
```

All 8 tests must pass for the task to be considered complete.

## Your Task

Identify and fix the defects in the runtime modules that cause the system to produce incorrect output. The configuration file (`indexer.ini`) contains the correct intended parameters. Focus your investigation on the Python source files in `/app/runtime/`.
