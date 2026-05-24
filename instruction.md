# Metrics Aggregation Repair — Operational Context

## Situation

A metrics aggregation runtime collects raw metric samples from distributed collectors, computes time-series aggregates (counters, histograms, gauges), and produces a consolidated metrics snapshot. The aggregator processes JSONL collector feeds, aligns timestamps to fixed intervals, groups samples into series, and exports the final aggregated state.

After a routine deployment, the exported snapshot exhibits several anomalies.

## Observed Symptoms

Running `python3 /app/runtime/run_aggregator.py` produces output that does not match expected aggregation behavior. The snapshot contains incorrect counter rates, inconsistent histogram totals, fewer series than expected, misaligned timestamps, and retains data that should have been filtered or evicted.

## Expected Behavior

After repair, the aggregation output must satisfy standard observability invariants for all metric types.

## Environment

The runtime environment already contains the required system-wide Python tooling and pytest installation.

## Key Files

- `/app/runtime/run_aggregator.py` — orchestration entrypoint
- `/app/runtime/aggregate.py` — core aggregation logic
- `/app/runtime/ingest.py` — JSONL collector feed loading
- `/app/runtime/export.py` — snapshot export with integrity checksum
- `/app/runtime/config/aggregator.ini` — aggregation interval, staleness threshold, cardinality settings
- `/app/runtime/collectors/` — raw metric samples from distributed sources
- `/app/runtime/output/metrics_snapshot.jsonl` — exported aggregated metrics snapshot
- `/app/runtime/output/snapshot_integrity.json` — export integrity metadata
- `/app/solution/repair_aggregator.py` — aggregation state repair script

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

## Output Schema: metrics_snapshot.jsonl

Each line is a JSON object representing one aggregated series. The `type` field determines the record structure:

**Counter records:**
- `type` (string) — always `"counter"`
- `metric` (string) — metric name
- `labels` (object) — full label key-value pairs
- `collector` (string) — source collector identifier
- `total_delta` (number) — cumulative delta across all intervals (must be non-negative)
- `intervals` (integer) — number of intervals contributing to the delta

**Histogram records:**
- `type` (string) — always `"histogram"`
- `metric` (string) — metric name
- `labels` (object) — full label key-value pairs
- `collector` (string) — source collector identifier
- `buckets` (object) — boundary-to-count mapping (e.g. `{"0.01": 80, "0.025": 210, ..., "+Inf": 700}`)
- `total_count` (integer) — total observation count (must equal `+Inf` bucket)
- `total_sum` (number) — sum of all observed values

**Gauge records:**
- `type` (string) — always `"gauge"`
- `metric` (string) — metric name
- `labels` (object) — full label key-value pairs
- `collector` (string) — source collector identifier
- `value` (number) — most recent gauge value
- `last_seen` (string) — ISO-8601 UTC timestamp of the most recent sample, aligned to 15-second boundary

## Output Schema: snapshot_integrity.json

- `sha256` (string) — SHA-256 digest over concatenated JSONL lines
- `record_count` (integer) — total records in the snapshot
- `counter_series` (integer) — number of counter series
- `histogram_series` (integer) — number of histogram series
- `gauge_series` (integer) — number of gauge series
- `exported_at` (string) — UTC timestamp of export
