"""Metrics aggregation behavioral tests.

Validates aggregation correctness against exported snapshot and state.
"""

import json
import hashlib
import os
from collections import Counter

RUNTIME_DIR = "/app/runtime"
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")
SNAPSHOT_PATH = os.path.join(OUTPUT_DIR, "metrics_snapshot.jsonl")
INTEGRITY_PATH = os.path.join(OUTPUT_DIR, "snapshot_integrity.json")


def load_snapshot():
    assert os.path.exists(SNAPSHOT_PATH), f"snapshot missing: {SNAPSHOT_PATH}"
    with open(SNAPSHOT_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_no_negative_counter_deltas():
    """Counter series must never have negative total_delta values."""
    records = load_snapshot()
    counters = [r for r in records if r["type"] == "counter"]
    assert len(counters) > 0, "no counter series in snapshot"

    negative = [c for c in counters if c["total_delta"] < 0]
    assert len(negative) == 0, (
        f"{len(negative)} counter series with negative deltas: "
        f"{[(c['metric'], c['total_delta']) for c in negative[:3]]}"
    )


def test_counter_reset_detection():
    """Counters that experience a value decrease must detect reset and report positive delta."""
    records = load_snapshot()
    counters = [r for r in records if r["type"] == "counter"]

    # find the east-1 api-gateway GET/200 counter (known to have a reset in data)
    east_get = [c for c in counters if c["collector"] == "east-1"
                and c["labels"].get("method") == "GET"
                and c["labels"].get("status") == "200"
                and c["metric"] == "http_requests_total"]
    assert len(east_get) == 1, "expected exactly one east-1 GET/200 counter series"

    # value goes 14823→14891→14950→42→105: reset at 42, correct delta = 68+59+42+63 = 232
    # with broken reset detection: delta = 68+59+(-14908)+63 = -14718
    assert east_get[0]["total_delta"] > 0, (
        f"east-1 GET/200 counter has delta {east_get[0]['total_delta']} — reset not detected"
    )


def test_histogram_bucket_monotonicity():
    """Histogram bucket counts must be monotonically non-decreasing across boundaries."""
    records = load_snapshot()
    histograms = [r for r in records if r["type"] == "histogram"]
    assert len(histograms) > 0, "no histogram series in snapshot"

    violations = 0
    for h in histograms:
        buckets = h["buckets"]
        numeric_keys = sorted(
            [(float(k) if k != "+Inf" else float("inf"), k) for k in buckets.keys()]
        )
        prev_count = 0
        for _, key in numeric_keys:
            if buckets[key] < prev_count:
                violations += 1
                break
            prev_count = buckets[key]

    assert violations == 0, f"{violations} histogram series with non-monotonic buckets"


def test_histogram_inf_equals_count():
    """The +Inf bucket must equal total_count for each histogram series."""
    records = load_snapshot()
    histograms = [r for r in records if r["type"] == "histogram"]

    mismatches = []
    for h in histograms:
        inf_val = h["buckets"].get("+Inf", 0)
        if inf_val != h["total_count"]:
            mismatches.append((h["metric"], h["collector"], inf_val, h["total_count"]))

    assert len(mismatches) == 0, (
        f"{len(mismatches)} histograms where +Inf != total_count: {mismatches[:3]}"
    )


def test_no_high_cardinality_labels():
    """No series in output should contain high-cardinality labels like request_id."""
    records = load_snapshot()
    high_card_labels = {"request_id", "trace_id", "span_id"}

    violations = []
    for r in records:
        labels = r.get("labels", {})
        found = high_card_labels & set(labels.keys())
        if found:
            violations.append((r["metric"], found))

    assert len(violations) == 0, (
        f"{len(violations)} series with high-cardinality labels: {violations[:3]}"
    )


def test_series_label_differentiation():
    """Series with different label sets must be separate in the output."""
    records = load_snapshot()
    counters = [r for r in records if r["type"] == "counter"]

    # group by metric+collector, check that different label combinations are distinct
    series_keys = []
    for c in counters:
        key = (c["metric"], c["collector"], json.dumps(c["labels"], sort_keys=True))
        series_keys.append(key)

    duplicates = [k for k, v in Counter(series_keys).items() if v > 1]
    assert len(duplicates) == 0, f"duplicate series keys found: {duplicates[:3]}"

    # specifically verify that east-1 has separate GET/200 and POST/201 series
    east_counters = [c for c in counters if c["collector"] == "east-1"
                     and c["metric"] == "http_requests_total"]
    assert len(east_counters) >= 2, (
        f"east-1 should have multiple http_requests_total series, found {len(east_counters)}"
    )


def test_timestamp_alignment():
    """All gauge last_seen timestamps must align to 15-second boundaries."""
    records = load_snapshot()
    gauges = [r for r in records if r["type"] == "gauge"]
    assert len(gauges) > 0, "no gauge series in snapshot"

    from datetime import datetime, timezone
    misaligned = []
    for g in gauges:
        ts = g["last_seen"]
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        epoch_s = int(dt.timestamp())
        if epoch_s % 15 != 0:
            misaligned.append((g["metric"], g["labels"].get("instance"), ts))

    assert len(misaligned) == 0, (
        f"{len(misaligned)} gauges with misaligned timestamps: {misaligned[:3]}"
    )


def test_gauge_staleness_eviction():
    """Gauges older than staleness threshold relative to the newest gauge must be evicted."""
    records = load_snapshot()
    gauges = [r for r in records if r["type"] == "gauge"]

    if not gauges:
        return

    from datetime import datetime, timezone
    timestamps = []
    for g in gauges:
        dt = datetime.fromisoformat(g["last_seen"].replace("Z", "+00:00"))
        timestamps.append((g, dt))

    latest_dt = max(dt for _, dt in timestamps)

    stale = []
    for g, dt in timestamps:
        age = (latest_dt - dt).total_seconds()
        if age > 60:
            stale.append((g["metric"], g["labels"].get("instance"), age))

    assert len(stale) == 0, f"{len(stale)} stale gauges not evicted: {stale[:3]}"


def test_counter_series_count():
    """Expected number of counter series after correct aggregation."""
    records = load_snapshot()
    counters = [r for r in records if r["type"] == "counter"]

    # with correct label differentiation and cardinality filtering:
    # east-1: GET/200, POST/201, cpu_total = 3 series
    # west-1: GET/200, GET/500 = 2 series
    # central-1: GET/200 (auth), cpu_total = 2 series
    # total = 7
    assert len(counters) == 7, (
        f"expected 7 counter series, got {len(counters)}"
    )


def test_snapshot_integrity_metadata():
    """snapshot_integrity.json must match actual snapshot content."""
    assert os.path.exists(INTEGRITY_PATH), "integrity file missing"
    assert os.path.exists(SNAPSHOT_PATH), "snapshot file missing"

    with open(INTEGRITY_PATH) as f:
        meta = json.load(f)

    line_count = 0
    hasher = hashlib.sha256()
    with open(SNAPSHOT_PATH) as f:
        for line in f:
            hasher.update(line.strip().encode("utf-8"))
            line_count += 1

    assert meta["record_count"] == line_count, (
        f"count mismatch: meta={meta['record_count']} actual={line_count}"
    )
    assert meta["sha256"] == hasher.hexdigest(), "hash mismatch in integrity metadata"


def test_total_record_count():
    """Total records must equal sum of counter + histogram + gauge series."""
    assert os.path.exists(INTEGRITY_PATH), "integrity file missing"

    with open(INTEGRITY_PATH) as f:
        meta = json.load(f)

    expected = meta["counter_series"] + meta["histogram_series"] + meta["gauge_series"]
    assert meta["record_count"] == expected, (
        f"record_count {meta['record_count']} != sum of series {expected}"
    )
