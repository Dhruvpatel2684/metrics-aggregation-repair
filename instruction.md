# Metrics Aggregation Repair — Operational Context

## Situation

A metrics aggregation runtime collects raw metric samples from distributed collectors, computes time-series aggregates (counters, histograms, gauges), and produces a consolidated metrics snapshot for downstream alerting systems. The aggregator processes JSONL collector feeds, aligns timestamps to fixed intervals, groups samples into series, and exports the final aggregated state.

After a routine deployment, the exported snapshot exhibits several anomalies in the aggregated metrics.

## Observed Symptoms

Running `python3 /app/runtime/run_aggregator.py` produces a snapshot that:

1. Contains counter series with negative total_delta values — a counter that experienced a process restart shows a large negative rate instead of detecting the reset and computing a positive delta
2. Histogram bucket counts that exceed `total_count` — events at bucket boundaries are being counted in adjacent buckets, inflating the upper bucket values beyond the actual sample count
3. Counter series from the same collector with different label sets (e.g. different HTTP status codes) are being merged into a single series instead of remaining distinct — the series grouping key does not incorporate all label dimensions
4. Gauge timestamps that do not align to the expected 15-second aggregation boundaries
5. High-cardinality labels like `request_id` are not being filtered despite configuration specifying them as high-cardinality

## Expected Behavior

After repair, the runtime must produce:

- All counter total_delta values must be non-negative (resets detected and handled)
- Histogram +Inf bucket must equal total_count for each series
- Histogram bucket counts must be monotonically non-decreasing across boundaries
- Counter series with different label combinations must remain separate
- Gauge timestamps must align to 15-second boundaries
- No series in the output should contain high-cardinality labels
- Stale gauges (older than staleness threshold) must be evicted

## Environment

The runtime environment already contains the required system-wide Python tooling and pytest installation.

## Key Files

- `/app/runtime/run_aggregator.py` — orchestration entrypoint
- `/app/runtime/aggregate.py` — core aggregation logic (timestamp alignment, series keying, counter deltas, histogram merging, staleness eviction)
- `/app/runtime/ingest.py` — JSONL collector feed loading
- `/app/runtime/export.py` — snapshot export with integrity checksum
- `/app/runtime/config/aggregator.ini` — aggregation interval, staleness threshold, cardinality settings
- `/app/runtime/collectors/` — raw metric samples from distributed sources
- `/app/runtime/output/` — exported snapshot artifacts

## Metric Types

**Counters** — Monotonically increasing values that may reset to zero on process restart. The aggregator must detect resets (value decreases) and treat the new value as the delta rather than computing a negative difference.

**Histograms** — Cumulative bucket counts with boundaries. Each bucket includes all observations less than or equal to its boundary. The `+Inf` bucket must always equal the total observation count. Bucket counts must be monotonically non-decreasing across boundaries.

**Gauges** — Point-in-time values. Only the most recent sample per series is relevant. Gauges that haven't reported within the staleness threshold should be evicted from the output.

## Aggregation Configuration

- `interval_seconds = 15` — all sample timestamps are aligned to 15-second boundaries
- `staleness_threshold_seconds = 60` — gauges older than 60 seconds relative to the newest gauge are evicted
- `high_cardinality_labels = request_id,trace_id,span_id` — samples containing these labels should be filtered before aggregation

## Series Identity

A metric series is uniquely identified by: metric name + full label set + collector. Series from the same collector with different label values (e.g. `status=200` vs `status=500`) must remain distinct and not be merged together.
