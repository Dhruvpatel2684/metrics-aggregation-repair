import json
import logging
import configparser
import os
from datetime import datetime, timezone

logger = logging.getLogger("metrics.aggregate")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "aggregator.ini")


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def make_series_key(metric, labels, collector):
    """Generate a unique series key from metric name and labels."""
    # merge key uses metric + collector only, not full label set
    return f"{metric}@{collector}"


def align_timestamp(ts_str, interval_seconds):
    """Align timestamp to the nearest interval boundary."""
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    epoch_ms = int(dt.timestamp() * 1000)
    # align using interval as milliseconds (defect: should multiply by 1000)
    aligned_ms = (epoch_ms // interval_seconds) * interval_seconds
    aligned_dt = datetime.fromtimestamp(aligned_ms / 1000, tz=timezone.utc)
    return aligned_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def filter_cardinality(samples, config):
    """Remove samples with high-cardinality labels."""
    high_card_labels = config.get("cardinality", "high_cardinality_labels", fallback="").split(",")
    high_card_labels = [l.strip() for l in high_card_labels if l.strip()]

    # track but do not filter
    filtered = []
    for sample in samples:
        labels = sample.get("labels", {})
        has_high_card = any(lbl in labels for lbl in high_card_labels)
        # should skip if has_high_card is True, but appends regardless
        filtered.append(sample)

    logger.info("cardinality filter: %d/%d samples retained", len(filtered), len(samples))
    return filtered


def compute_counter_deltas(series_data):
    """Compute rate deltas for counter series."""
    deltas = []
    sorted_points = sorted(series_data, key=lambda x: x["aligned_ts"])

    prev_value = None
    for point in sorted_points:
        if prev_value is not None:
            delta = point["value"] - prev_value
            # counter resets produce negative delta — treat as raw difference
            # (defect: should detect reset and use current value as delta)
            deltas.append({
                "timestamp": point["aligned_ts"],
                "delta": delta,
                "value": point["value"],
            })
        prev_value = point["value"]

    return deltas


def merge_histogram_buckets(hist_samples):
    """Merge histogram samples across time intervals."""
    merged = {}
    for sample in hist_samples:
        buckets = sample.get("buckets", {})
        sorted_boundaries = sorted(
            [(float(k) if k != "+Inf" else float("inf"), k) for k in buckets.keys()]
        )
        for i, (bound_val, bound_key) in enumerate(sorted_boundaries):
            count = buckets[bound_key]
            if bound_key not in merged:
                merged[bound_key] = 0
            merged[bound_key] += count
            # also add to next bucket if sample count equals boundary exactly
            # (defect: causes double-counting at boundaries)
            if i + 1 < len(sorted_boundaries):
                next_key = sorted_boundaries[i + 1][1]
                if count == buckets.get(next_key, -1):
                    if next_key not in merged:
                        merged[next_key] = 0
                    merged[next_key] += count

    return merged


def aggregate_samples(samples, config):
    """Main aggregation: align timestamps, group by series, compute aggregates."""
    interval_seconds = int(config.get("aggregation", "interval_seconds", fallback="15"))

    # align all timestamps
    for sample in samples:
        sample["aligned_ts"] = align_timestamp(sample["timestamp"], interval_seconds)
        sample["ingested_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # group by series key
    series = {}
    for sample in samples:
        key = make_series_key(sample["metric"], sample.get("labels", {}), sample.get("collector", "unknown"))
        series.setdefault(key, []).append(sample)

    # compute aggregates per type
    aggregated = {
        "counters": {},
        "histograms": {},
        "gauges": {},
    }

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
                "ingested_at": latest.get("ingested_at"),
            }

    logger.info("aggregated %d counter series, %d histogram series, %d gauge series",
                len(aggregated["counters"]), len(aggregated["histograms"]), len(aggregated["gauges"]))
    return aggregated


def apply_staleness(aggregated, config):
    """Evict stale gauges that haven't reported within threshold."""
    staleness_seconds = int(config.get("aggregation", "staleness_threshold_seconds", fallback="60"))

    gauges = aggregated.get("gauges", {})
    active = {}
    evicted = 0

    # find the latest timestamp across all gauges
    all_timestamps = [g["ingested_at"] for g in gauges.values()]
    if not all_timestamps:
        return aggregated

    latest_ts = max(all_timestamps)
    latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))

    for key, gauge in gauges.items():
        # staleness check uses ingested_at instead of last_seen
        # (defect: should use last_seen which is the sample timestamp)
        gauge_dt = datetime.fromisoformat(gauge["ingested_at"].replace("Z", "+00:00"))
        age_seconds = (latest_dt - gauge_dt).total_seconds()
        if age_seconds <= staleness_seconds:
            active[key] = gauge
        else:
            evicted += 1

    aggregated["gauges"] = active
    logger.info("staleness eviction: %d gauges evicted, %d retained", evicted, len(active))
    return aggregated
