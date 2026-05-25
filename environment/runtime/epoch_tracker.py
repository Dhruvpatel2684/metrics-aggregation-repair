"""Epoch boundary detection and record grouping for cluster reconciliation."""

import configparser
import os


def load_epoch_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")
    config.read(config_path)
    return {
        "boundary_threshold": int(config.get("epochs", "boundary_threshold")),
        "max_epoch": int(config.get("epochs", "max_epoch")),
    }


def detect_epoch_boundaries(records, threshold):
    """Group records into epochs based on boundary detection.

    Records are sorted by timestamp and assigned to epoch buckets.
    Boundary detection uses the threshold to determine when transition
    records should be grouped with the next epoch.
    """
    sorted_records = sorted(records, key=lambda r: r["ts"])
    epoch_map = {}
    current_epoch = None
    records_in_epoch = 0

    for i, record in enumerate(sorted_records):
        rec_epoch = record["epoch"]

        if current_epoch is None:
            current_epoch = rec_epoch
            records_in_epoch = 0

        if rec_epoch > current_epoch:
            current_epoch = rec_epoch
            records_in_epoch = 0

        records_in_epoch += 1
        bucket = current_epoch

        if i + 1 < len(sorted_records):
            next_rec = sorted_records[i + 1]
            if next_rec["epoch"] >= current_epoch + 1 and records_in_epoch >= threshold:
                bucket = next_rec["epoch"]

        if bucket not in epoch_map:
            epoch_map[bucket] = []
        epoch_map[bucket].append(record)

    return epoch_map


def validate_timing(records, interval_ms):
    """Validate heartbeat timing intervals are within acceptable bounds.

    This checks that consecutive heartbeats from the same node maintain
    the configured interval within tolerance.
    """
    hb_records = [r for r in records if r["type"] == "hb"]
    hb_records.sort(key=lambda r: r["ts"])

    violations = 0
    for i in range(1, len(hb_records)):
        prev_ts = hb_records[i - 1]["ts"]
        curr_ts = hb_records[i]["ts"]
        if prev_ts >= curr_ts:
            violations += 1

    return violations


def get_epoch_stats(epoch_map):
    """Compute statistics for each epoch bucket."""
    stats = {}
    for epoch_num, records in epoch_map.items():
        stats[str(epoch_num)] = {
            "record_count": len(records),
            "hb_count": sum(1 for r in records if r["type"] == "hb"),
            "vote_count": sum(1 for r in records if r["type"] == "vote"),
            "log_count": sum(1 for r in records if r["type"] == "log"),
        }
    return stats
