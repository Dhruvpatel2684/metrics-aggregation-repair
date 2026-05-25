"""Log replication and heartbeat window processing.

Processes heartbeat acknowledgments in configurable windows and
aggregates log entry replication state. This module uses timing.strict
parameters for consistency checks across the cluster.
"""

import configparser
import os
import json


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")


def load_replication_config():
    """Load replication window configuration."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    window_size = config.getint("replication", "window_size")
    return {"window_size": window_size}


def process_heartbeat_windows(records):
    """Process heartbeat records in sliding windows.

    Records are processed in batches defined by window_size.
    Each window produces aggregated ack_count for the entries within it.
    """
    config = load_replication_config()
    window_size = config["window_size"]

    heartbeats = [r for r in records if r.get("type") == "heartbeat"]

    if not heartbeats:
        return []

    results = []
    ack_count = 0

    for i in range(0, len(heartbeats), window_size):
        window = heartbeats[i:i + window_size]

        # Aggregate acknowledgment counts for this window
        window_acks = sum(h.get("ack_count", 0) for h in window)
        ack_count += window_acks

        results.append({
            "window_start": window[0]["timestamp"],
            "window_end": window[-1]["timestamp"],
            "window_records": len(window),
            "ack_count": ack_count,
            "leader_id": window[-1].get("leader_id", "unknown")
        })

    return results


def replicate_logs(records, config=None):
    """Process log entries and compute replication state.

    Combines heartbeat window processing with log entry tracking
    to produce a complete replication picture.
    """
    if config is None:
        config = load_replication_config()

    # Process heartbeat windows
    windows = process_heartbeat_windows(records)

    # Process log entries
    log_entries = [r for r in records if r.get("type") == "log_entry"]

    committed = []
    for entry in log_entries:
        # Use the latest window ack_count for this entry
        relevant_windows = [w for w in windows if w["window_end"] <= entry["timestamp"]]

        if relevant_windows:
            latest_window = relevant_windows[-1]
            entry_ack = latest_window["ack_count"]
        else:
            entry_ack = entry.get("ack_count", 0)

        committed.append({
            "index": entry["index"],
            "term": entry["term"],
            "node_id": entry["node_id"],
            "timestamp": entry["timestamp"],
            "operation": entry["operation"],
            "ack_count": entry_ack
        })

    return committed
