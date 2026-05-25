"""Time-series compaction engine entry point.

Orchestrates the full compaction workflow: configuration loading,
collector filtering, metric ingestion from TSV sources, multi-tier
rollup processing, deterministic sorting, and output generation.
"""
import hashlib
import json
import os
import sys

from runtime.config import get_config
from runtime.collector_filter import get_active_collectors, filter_metrics
from runtime.aligner import get_alignment_offset
from runtime.rollup import CompactionEngine
from runtime.sorter import sort_compacted_points
from runtime.hasher import compute_integrity_hash


def load_tsv_data(data_dir):
    """Load all TSV metric files from the data directory.
    
    Parses tab-separated files with header: ts, collector, metric, value
    
    Returns:
        list of metric record dicts
    """
    records = []
    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith(".tsv"):
            continue
        fpath = os.path.join(data_dir, fname)
        with open(fpath, "r") as f:
            header = f.readline().strip().split("\t")
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                record = {
                    "ts": int(parts[0]),
                    "collector": parts[1],
                    "metric": parts[2],
                    "value": float(parts[3])
                }
                records.append(record)
    return records


def run():
    """Execute the compaction workflow."""
    config = get_config()
    
    # Resolve paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.exists("/app/runtime"):
        base_dir = "/app"
    data_dir = os.path.join(base_dir, "runtime", "data")
    output_dir = os.path.join(base_dir, "runtime", "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Load and filter metrics
    all_records = load_tsv_data(data_dir)
    active_collectors = get_active_collectors()
    
    # Get registered collectors for report
    registered = config.get("collectors", "registered").split(",")
    
    filtered_records = filter_metrics(all_records, active_collectors)
    
    # Run compaction engine
    engine = CompactionEngine()
    result = engine.compact(filtered_records)
    
    # Sort output deterministically
    sorted_points = sort_compacted_points(result["points"])
    
    # Build compaction report
    report = {
        "engine_id": config.get("engine", "engine_id"),
        "total_collectors": len(registered),
        "active_collectors": len(active_collectors),
        "retention_tiers": len(result["tier_stats"]),
        "alignment_offset_ms": get_alignment_offset(),
        "points_ingested": len(filtered_records),
        "points_compacted": len(sorted_points),
        "tier_stats": result["tier_stats"]
    }
    
    # Compute integrity hash
    report["integrity_hash"] = compute_integrity_hash(report)
    
    # Build series output
    series_canonical = json.dumps(sorted_points, sort_keys=True, separators=(",", ":"))
    series_hash = hashlib.sha256(series_canonical.encode()).hexdigest()[:16]
    
    series_output = {
        "series_hash": series_hash,
        "points": sorted_points
    }
    
    # Write outputs
    report_path = os.path.join(output_dir, "compaction_report.json")
    series_path = os.path.join(output_dir, "compacted_series.json")
    
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    with open(series_path, "w") as f:
        json.dump(series_output, f, indent=2)
    
    print(f"Compaction complete: {len(sorted_points)} points written")
    print(f"Report: {report_path}")
    print(f"Series: {series_path}")


if __name__ == "__main__":
    run()
