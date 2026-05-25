"""Main orchestrator for Raft election reconciliation system."""

import configparser
import json
import os
import sys


def load_cluster_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")
    config.read(config_path)
    return config


def load_stream_data():
    """Load all JSONL stream files from the data directory."""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    all_records = []

    for filename in sorted(os.listdir(data_dir)):
        if filename.endswith(".jsonl"):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_records.append(json.loads(line))

    return all_records


def build_commitment_entries(merged_logs, epoch_map, reconciliation_results):
    """Build commitment manifest entries from merged log data."""
    commit_acks = reconciliation_results["commit"]["total_acks"]
    entries_committed = reconciliation_results["commit"]["entries_committed"]

    if entries_committed > 0:
        base_ack = commit_acks // entries_committed
    else:
        base_ack = 0

    entries = []
    for log_entry in merged_logs:
        entry_epoch = log_entry.get("epoch", 0)
        entries.append({
            "index": log_entry["idx"],
            "ts": log_entry["ts"],
            "nid": log_entry["nid"],
            "term": log_entry["term"],
            "op": log_entry["op"],
            "phase": "commit",
            "ack_count": base_ack,
            "epoch": entry_epoch,
        })

    return entries


def main():
    from runtime import epoch_tracker
    from runtime import registry
    from runtime import reconciler
    from runtime import merger
    from runtime import consensus
    from runtime import hasher

    config = load_cluster_config()

    all_records = load_stream_data()

    epoch_config = epoch_tracker.load_epoch_config()
    epoch_map = epoch_tracker.detect_epoch_boundaries(
        all_records, epoch_config["boundary_threshold"]
    )

    epoch_stats = epoch_tracker.get_epoch_stats(epoch_map)

    recon_config = reconciler.load_reconciliation_config()
    reconciliation_results = reconciler.reconcile(
        all_records, epoch_map, recon_config["window_size"]
    )

    merged_logs = merger.merge_and_deduplicate(all_records)

    vote_records = [r for r in all_records if r["type"] == "vote"]
    valid_votes = registry.count_valid_votes(vote_records)
    quorum_result = consensus.check_quorum(valid_votes)

    current_epoch = max(int(e) for e in epoch_stats.keys())

    commitment_entries = build_commitment_entries(
        merged_logs, epoch_map, reconciliation_results
    )

    manifest_hash = hasher.hash_manifest(commitment_entries)

    reconciliation_state = {
        "cluster_id": config.get("cluster", "cluster_id"),
        "total_nodes": int(config.get("cluster", "total_nodes")),
        "active_voters": quorum_result["active_voters"],
        "quorum_reached": quorum_result["quorum_reached"],
        "quorum_size": quorum_result["quorum_size"],
        "leader_node": config.get("cluster", "leader_node"),
        "current_epoch": current_epoch,
        "epoch_stats": epoch_stats,
        "reconciliation": reconciliation_results,
        "integrity_hash": "",
    }

    reconciliation_state["integrity_hash"] = hasher.hash_state(reconciliation_state)

    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    state_path = os.path.join(output_dir, "reconciliation_state.json")
    with open(state_path, "w") as f:
        json.dump(reconciliation_state, f, indent=2)

    manifest = {
        "manifest_hash": manifest_hash,
        "entries": commitment_entries,
    }

    manifest_path = os.path.join(output_dir, "commitment_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Reconciliation complete. Epoch range: 5-{current_epoch}")
    print(f"Output written to {output_dir}")


if __name__ == "__main__":
    main()
