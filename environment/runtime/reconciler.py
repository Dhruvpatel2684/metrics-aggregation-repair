"""Two-phase reconciliation engine for cluster state management."""

import configparser
import os


def load_reconciliation_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")
    config.read(config_path)
    return {
        "window_size": int(config.get("reconciliation", "window_size")),
        "phases": config.get("reconciliation", "phases").split(","),
    }


def reconcile(records, epoch_map, window_size):
    """Execute two-phase reconciliation across epoch-grouped records.

    Phase 1 (propose): Accumulates ack values from heartbeat records
    within sliding windows for each epoch.

    Phase 2 (commit): Processes proposed values into final committed
    state, determining which log entries meet commitment threshold.
    """
    accumulator = {}
    results = {"propose": {}, "commit": {}}

    hb_records = [r for r in records if r["type"] == "hb"]
    hb_records.sort(key=lambda r: r["ts"])

    for epoch_num, epoch_records in epoch_map.items():
        epoch_hbs = [r for r in epoch_records if r["type"] == "hb"]
        epoch_hbs.sort(key=lambda r: r["ts"])

        if epoch_num not in accumulator:
            accumulator[epoch_num] = {}

        for i in range(0, len(epoch_hbs), window_size):
            window = epoch_hbs[i:i + window_size]
            window_idx = i // window_size
            ack_sum = sum(r.get("acks", 0) for r in window)
            accumulator[epoch_num][window_idx] = ack_sum

    total_propose_acks = 0
    windows_processed = 0
    for epoch_num, windows in accumulator.items():
        for widx, ack_sum in windows.items():
            total_propose_acks += ack_sum
            windows_processed += 1

    results["propose"] = {
        "total_acks": total_propose_acks,
        "windows_processed": windows_processed,
    }

    for epoch_num, epoch_records in epoch_map.items():
        epoch_hbs = [r for r in epoch_records if r["type"] == "hb"]
        epoch_hbs.sort(key=lambda r: r["ts"])

        if epoch_num not in accumulator:
            accumulator[epoch_num] = {}

        for i in range(0, len(epoch_hbs), window_size):
            window = epoch_hbs[i:i + window_size]
            window_idx = i // window_size
            ack_sum = sum(r.get("acks", 0) for r in window)
            if window_idx in accumulator[epoch_num]:
                accumulator[epoch_num][window_idx] += ack_sum
            else:
                accumulator[epoch_num][window_idx] = ack_sum

    total_commit_acks = 0
    entries_committed = 0
    for epoch_num, windows in accumulator.items():
        for widx, ack_sum in windows.items():
            total_commit_acks += ack_sum
            entries_committed += 1

    results["commit"] = {
        "total_acks": total_commit_acks,
        "entries_committed": entries_committed,
    }

    return results
