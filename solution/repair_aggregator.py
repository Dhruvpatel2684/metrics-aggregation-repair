#!/usr/bin/env python3
"""Metrics aggregation repair.

Fixes corrupted aggregation state by re-processing samples with correct logic:
- Counter reset detection
- Histogram bucket boundary semantics
- Staleness eviction using sample timestamps
- High-cardinality label filtering
- Correct timestamp alignment (seconds, not milliseconds)
- Full label dimensions in series merge key
"""

import json
import hashlib
import os
import sys
import logging
import configparser
import glob
from datetime import datetime, timezone

RUNTIME_DIR = "/app/runtime"
CONFIG_PATH = os.path.join(RUNTIME_DIR, "config", "aggregator.ini")
COLLECTORS_DIR = os.path.join(RUNTIME_DIR, "collectors")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("repair.aggregator")


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def load_samples():
    pattern = os.path.join(COLLECTORS_DIR, "collector_*.jsonl")
    files = sorted(glob.glob(pattern))
    samples = []
    for fpath in files:
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                samples.append(json.loads(line))
    return samples


def make_series_key(metric, labels, collector):
    """Correct merge key: metric + ALL labels + collector."""
    sorted_labels = sorted(labels.items())
    label_str = ",".join(f"{k}={v}" for k, v in sorted_labels)
    return f"{metric}{{{label_str}}}@{collector}"


def align_timestamp(ts_str, interval_seconds):
    """Correct alignment: convert interval to milliseconds for epoch math."""
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    epoch_ms = int(dt.timestamp() * 1000)
    interval_ms = interval_seconds * 1000
    aligned_ms = (epoch_ms // interval_ms) * interval_ms
    aligned_dt = datetime.fromtimestamp(aligned_ms / 1000, tz=timezone.utc)
    return aligned_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def filter_cardinality(samples, config):
    """Correct cardinality filter: remove samples with high-cardinality labels."""
    high_card_labels = config.get("cardinality", "high_cardinality_labels", fallback="").split(",")
    high_card_labels = [l.strip() for l in high_card_labels if l.strip()]

    filtered = []
    for sample in samples:
        labels = sample.get("labels", {})
        has_high_card = any(lbl in labels for lbl in high_card_labels)
        if not has_high_card:
            filtered.append(sample)

    logger.info("cardinality filter: %d/%d samples retained", len(filtered), len(samples))
    return filtered


def compute_counter_deltas(series_data):
    """Correct counter delta: detect resets and use value as delta."""
    deltas = []
    sorted_points = sorted(series_data, key=lambda x: x["aligned_ts"])

    prev_value = None
    for point in sorted_points:
        if prev_value is not None:
            delta = point["value"] - prev_value
            if delta < 0:
                # counter reset detected — use current value as delta
                delta = point["value"]
            deltas.append({
                "timestamp": point["aligned_ts"],
                "delta": delta,
                "value": point["value"],
            })
        prev_value = point["value"]

    return deltas


def merge_histogram_buckets(hist_samples):
    """Correct histogram merge: simple sum per bucket, no double-counting."""
    merged = {}
    for sample in hist_samples:
        buckets = sample.get("buckets", {})
        for boundary, count in buckets.items():
            if boundary not in merged:
                merged[boundary] = 0
            merged[boundary] += count
    return merged


def main():
    logger.info("metrics aggregation repair starting")

    if not os.path.exists(CONFIG_PATH):
        logger.error("config not found at %s", CONFIG_PATH)
        sys.exit(1)

    config = load_config()
    interval_seconds = int(config.get("aggregation", "interval_seconds", fallback="15"))
    staleness_seconds = int(config.get("aggregation", "staleness_threshold_seconds", fallback="60"))

    samples = load_samples()
    if not samples:
        logger.error("no samples found")
        sys.exit(1)

    # filter high-cardinality
    samples = filter_cardinality(samples, config)

    # align timestamps correctly
    for sample in samples:
        sample["aligned_ts"] = align_timestamp(sample["timestamp"], interval_seconds)

    # group by correct series key (includes all labels)
    series = {}
    for sample in samples:
        key = make_series_key(sample["metric"], sample.get("labels", {}), sample.get("collector", "unknown"))
        series.setdefault(key, []).append(sample)

    # aggregate
    aggregated = {"counters": {}, "histograms": {}, "gauges": {}}

    for key, points in series.items():
        metric_type = points[0]["type"]

        if metric_type == "counter":
            deltas = compute_counter_deltas(points)
            if deltas:
                aggregated["counters"][key] = {
                    "metric": points[0]["metric"],
                    "labels": points[0]["labels"],
                    "collector": points[0].get("collector"),
                    "deltas": deltas,
                    "total_delta": sum(d["delta"] for d in deltas),
                }

        elif metric_type == "histogram":
            merged_buckets = merge_histogram_buckets(points)
            total_count = sum(s.get("count", 0) for s in points)
            total_sum = sum(s.get("sum", 0) for s in points)
            aggregated["histograms"][key] = {
                "metric": points[0]["metric"],
                "labels": points[0]["labels"],
                "collector": points[0].get("collector"),
                "buckets": merged_buckets,
                "total_count": total_count,
                "total_sum": total_sum,
            }

        elif metric_type == "gauge":
            latest = max(points, key=lambda x: x["aligned_ts"])
            aggregated["gauges"][key] = {
                "metric": points[0]["metric"],
                "labels": points[0]["labels"],
                "collector": points[0].get("collector"),
                "value": latest["value"],
                "last_seen": latest["aligned_ts"],
            }

    # staleness eviction using last_seen (sample timestamp)
    gauges = aggregated.get("gauges", {})
    if gauges:
        all_ts = [g["last_seen"] for g in gauges.values()]
        latest_ts = max(all_ts)
        latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))

        active_gauges = {}
        for key, gauge in gauges.items():
            gauge_dt = datetime.fromisoformat(gauge["last_seen"].replace("Z", "+00:00"))
            age = (latest_dt - gauge_dt).total_seconds()
            if age <= staleness_seconds:
                active_gauges[key] = gauge

        aggregated["gauges"] = active_gauges
        logger.info("staleness: %d evicted, %d retained",
                    len(gauges) - len(active_gauges), len(active_gauges))

    # export
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    snapshot_path = os.path.join(OUTPUT_DIR, "metrics_snapshot.jsonl")
    integrity_path = os.path.join(OUTPUT_DIR, "snapshot_integrity.json")

    hasher = hashlib.sha256()
    record_count = 0

    with open(snapshot_path, "w") as f:
        for key in sorted(aggregated["counters"].keys()):
            data = aggregated["counters"][key]
            record = {
                "type": "counter",
                "metric": data["metric"],
                "labels": data["labels"],
                "collector": data["collector"],
                "total_delta": data["total_delta"],
                "intervals": len(data["deltas"]),
            }
            line = json.dumps(record, separators=(",", ":"), sort_keys=True)
            f.write(line + "\n")
            hasher.update(line.encode("utf-8"))
            record_count += 1

        for key in sorted(aggregated["histograms"].keys()):
            data = aggregated["histograms"][key]
            record = {
                "type": "histogram",
                "metric": data["metric"],
                "labels": data["labels"],
                "collector": data["collector"],
                "buckets": data["buckets"],
                "total_count": data["total_count"],
                "total_sum": data["total_sum"],
            }
            line = json.dumps(record, separators=(",", ":"), sort_keys=True)
            f.write(line + "\n")
            hasher.update(line.encode("utf-8"))
            record_count += 1

        for key in sorted(aggregated["gauges"].keys()):
            data = aggregated["gauges"][key]
            record = {
                "type": "gauge",
                "metric": data["metric"],
                "labels": data["labels"],
                "collector": data["collector"],
                "value": data["value"],
                "last_seen": data["last_seen"],
            }
            line = json.dumps(record, separators=(",", ":"), sort_keys=True)
            f.write(line + "\n")
            hasher.update(line.encode("utf-8"))
            record_count += 1

    integrity = {
        "sha256": hasher.hexdigest(),
        "record_count": record_count,
        "counter_series": len(aggregated["counters"]),
        "histogram_series": len(aggregated["histograms"]),
        "gauge_series": len(aggregated["gauges"]),
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    with open(integrity_path, "w") as f:
        json.dump(integrity, f, indent=2)

    logger.info("repair complete: %d records exported", record_count)


if __name__ == "__main__":
    main()
