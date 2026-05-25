# Time-Series Database Compaction Engine

## Overview

This system implements a multi-tier retention compaction engine for high-frequency
time-series metric data. It processes raw metric streams from distributed collectors,
applies configurable window-based downsampling across multiple retention tiers, and
produces deterministic compacted output with integrity verification.

Global system-wide tooling ensures consistent behavior across all processing stages,
from collector registry management through final output serialization.

## Architecture

The compaction engine operates as a batch processor that ingests tab-separated metric
data from multiple collector sources, filters against the active collector registry,
and applies progressive downsampling through configurable retention tiers.

### Processing Flow

1. **Configuration Loading**: INI-based configuration provides collector registry,
   windowing parameters, retention tier definitions, and output settings.

2. **Collector Filtering**: The active collector registry determines which metric
   sources participate in compaction. Only metrics from registered active collectors
   are processed.

3. **Metric Ingestion**: Raw metric data is loaded from TSV files in the data
   directory. Each record contains a millisecond-precision epoch timestamp,
   collector identifier, metric name, and numeric value.

4. **Window Alignment**: Timestamps are aligned to window boundaries using the
   precise windowing configuration. The alignment offset compensates for any
   boundary shift in the bucket calculation.

5. **Multi-Tier Rollup**: Metrics pass through each retention tier independently.
   Each tier defines a window size (raw=1s, medium=60s, coarse=300s) and computes
   windowed mean aggregates. Each retention tier processes independently with reset
   aggregation state to ensure tier isolation.

6. **Deterministic Sorting**: The final point set is sorted to guarantee reproducible
   output. Deterministic ordering uses (timestamp, collector_id, metric_name) composite
   key to ensure stable output regardless of processing order.

7. **Integrity Hashing**: A SHA-256 based integrity hash captures the canonical state
   of the compaction report, enabling downstream systems to detect any divergence.

## Configuration

The system uses a sectioned INI configuration file (`retention.ini`) with the
following structure:

### Engine Section
- `engine_id`: Unique identifier for the compaction engine instance
- `version`: Engine version string

### Collectors Section
- `registered`: Comma-separated list of all known collector identifiers
- `active_collectors`: Comma-separated list of currently active collectors

### Windowing Section
- `alignment_offset_ms`: Offset applied during timestamp alignment
- `window_strategy`: Windowing strategy (fixed or sliding)
- `boundary_mode`: Boundary handling mode for precise alignment

### Retention Section
- `tiers`: Ordered list of retention tier names
- `{tier}_window_ms`: Window size in milliseconds for each tier

### Output Section
- `format`: Output serialization format
- `precision`: Decimal precision for aggregated values
- `base_path`: Base directory for output files

## Input Format

Metric data files use tab-separated values (TSV) format:

```
ts	collector	metric	value
1710500001000	cpu_host	cpu_usage	45.2
1710500013000	cpu_host	cpu_usage	47.8
```

Fields:
- `ts`: Epoch timestamp in milliseconds (integer)
- `collector`: Collector identifier string
- `metric`: Metric name string
- `value`: Numeric metric value (floating point)

## Output Schema

### Compaction Report (`compaction_report.json`)

```json
{
  "engine_id": "tsdb-compact-v3",
  "total_collectors": 4,
  "active_collectors": 4,
  "retention_tiers": 3,
  "alignment_offset_ms": 0,
  "points_ingested": 67,
  "points_compacted": 92,
  "tier_stats": {
    "raw": {"points": 67, "window_ms": 1000},
    "medium": {"points": 19, "window_ms": 60000},
    "coarse": {"points": 6, "window_ms": 300000}
  },
  "integrity_hash": "<16-char hex SHA-256 prefix>"
}
```

Fields:
- `engine_id`: Engine instance identifier from configuration
- `total_collectors`: Count of all registered collectors
- `active_collectors`: Count of active collectors contributing metrics
- `retention_tiers`: Number of retention tiers processed
- `alignment_offset_ms`: Alignment offset used for window computation
- `points_ingested`: Number of metric points after collector filtering
- `points_compacted`: Total compacted points across all tiers
- `tier_stats`: Per-tier statistics including point count and window size
- `integrity_hash`: First 16 hex characters of SHA-256 over canonical report

### Compacted Series (`compacted_series.json`)

```json
{
  "series_hash": "<16-char hex SHA-256 prefix>",
  "points": [
    {
      "ts": 1710499800000,
      "collector": "cpu_host",
      "metric": "cpu_usage",
      "value": 54.57,
      "tier": "raw",
      "window_start": 1710499800000
    }
  ]
}
```

Fields per point:
- `ts`: Window-aligned timestamp in milliseconds
- `collector`: Source collector identifier
- `metric`: Metric name
- `value`: Aggregated mean value (rounded to 2 decimal places)
- `tier`: Retention tier that produced this point
- `window_start`: Start of the aggregation window

## Retention Tiers

The system processes three retention tiers with progressively larger windows:

| Tier   | Window Size | Purpose                          |
|--------|-------------|----------------------------------|
| raw    | 1 second    | Per-second granularity           |
| medium | 60 seconds  | Minute-level downsampling        |
| coarse | 300 seconds | Five-minute summary aggregation  |

Each tier independently processes all filtered input records, computing windowed
mean values for each unique (window_start, collector, metric) combination within
that tier's window size.

## Integrity Verification

The integrity hash provides tamper detection for the compaction report. It is
computed by:

1. Extracting all report fields except the hash itself
2. Serializing to canonical JSON (sorted keys, compact separators)
3. Computing SHA-256 of the UTF-8 encoded canonical string
4. Taking the first 16 hexadecimal characters of the digest

The series output includes a separate hash computed over the canonical JSON
representation of the sorted points array.

## Collector Registry

The system maintains a registry of known metric collectors. The configuration
distinguishes between all registered collectors and the subset that are currently
active. Only metrics from active collectors pass through the ingestion filter.

Collector identifiers must match exactly between the configuration registry and
the collector field in metric data records for proper filtering.

## Window Alignment

Window alignment ensures that timestamps map deterministically to window
boundaries. The alignment formula is:

```
window_start = ((ts - offset) // window_ms) * window_ms + offset
```

Where `offset` is the configured alignment offset and `window_ms` is the tier's
window size. With offset=0 (precise mode), this simplifies to standard floor
division to the nearest window boundary.

## Execution

Run the compaction engine:

```bash
python3 -m runtime.run_compactor
```

The engine reads from `/app/runtime/data/` and writes to `/app/runtime/output/`.

## System Requirements

- Python 3.11 or later
- Standard library only (no external dependencies)
- Input data in TSV format with proper headers
- Writable output directory
