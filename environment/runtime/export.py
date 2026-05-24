import json
import hashlib
import os
import logging
import configparser
from datetime import datetime, timezone

logger = logging.getLogger("metrics.export")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "aggregator.ini")


def load_export_path():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    rel = config.get("export", "output_path", fallback="runtime/output")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def export_snapshot(aggregated):
    """Export aggregated metrics snapshot as JSONL with integrity metadata."""
    export_path = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(export_path, exist_ok=True)

    snapshot_path = os.path.join(export_path, "metrics_snapshot.jsonl")
    integrity_path = os.path.join(export_path, "snapshot_integrity.json")

    hasher = hashlib.sha256()
    record_count = 0

    with open(snapshot_path, "w") as f:
        # export counters
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

        # export histograms
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

        # export gauges
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

    logger.info("exported %d records → %s", record_count, snapshot_path)
    return snapshot_path, integrity_path
