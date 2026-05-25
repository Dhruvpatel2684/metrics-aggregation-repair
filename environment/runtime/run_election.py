"""Raft election verification system - main orchestrator.

Processes cluster node data files to produce a health report
and committed entries manifest.
"""

import json
import os
import sys
import glob

# Ensure proper import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.voter import count_votes, get_active_voter_count, get_quorum_size
from runtime.timer import get_election_timeout, validate_election_timing
from runtime.log_replicator import replicate_logs
from runtime.merger import merge_events, merge_log_entries


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")


def load_node_data():
    """Load all node data files from the data directory."""
    all_records = []
    pattern = os.path.join(DATA_DIR, "node_*.json")

    for filepath in sorted(glob.glob(pattern)):
        with open(filepath) as f:
            records = json.load(f)
            all_records.extend(records)

    return all_records


def load_cluster_config():
    """Load cluster-level configuration."""
    import configparser
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def build_cluster_health(records, config):
    """Build the cluster health report."""
    # Count votes
    election_events = [r for r in records if r.get("type") == "election"]
    vote_counts = count_votes(election_events)

    # Determine leader (candidate with most votes)
    leader = config.get("cluster", "leader_node") if not vote_counts else max(vote_counts, key=vote_counts.get)

    # Get election term from latest election event
    election_terms = [r.get("term", 0) for r in election_events]
    current_term = max(election_terms) if election_terms else 0

    # Calculate average heartbeat interval
    heartbeats = [r for r in records if r.get("type") == "heartbeat"]
    if len(heartbeats) >= 2:
        from datetime import datetime
        timestamps = sorted([datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00")) for h in heartbeats])
        deltas = [(timestamps[i+1] - timestamps[i]).total_seconds() * 1000 for i in range(len(timestamps)-1)]
        avg_heartbeat = sum(deltas) / len(deltas) if deltas else 0.0
    else:
        avg_heartbeat = 0.0

    # Get timeout from timer module
    timeout_ms = get_election_timeout()

    # Get voter info
    active_voters = get_active_voter_count()
    quorum = get_quorum_size()
    total_votes = sum(vote_counts.values()) if vote_counts else 0

    # Count committed entries
    log_entries = [r for r in records if r.get("type") == "log_entry"]
    committed_count = len(set(e.get("index") for e in log_entries))

    return {
        "cluster_id": config.get("cluster", "cluster_id"),
        "total_nodes": config.getint("cluster", "total_nodes"),
        "active_voters": active_voters,
        "quorum_reached": total_votes >= quorum,
        "leader_node": leader,
        "election_term": current_term,
        "avg_heartbeat_ms": round(avg_heartbeat, 2),
        "election_timeout_ms": timeout_ms,
        "committed_count": committed_count
    }


def build_committed_entries(records):
    """Build the committed entries manifest."""
    # Get committed entries from log replicator
    committed = replicate_logs(records)

    # Merge entries from all nodes using merger
    merged = merge_log_entries(committed)

    return merged


def main():
    """Run the election verification system."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    records = load_node_data()
    if not records:
        print("ERROR: No node data found")
        sys.exit(1)

    config = load_cluster_config()

    # Build health report
    health = build_cluster_health(records, config)

    # Build committed entries
    committed = build_committed_entries(records)

    # Write outputs
    health_path = os.path.join(OUTPUT_DIR, "cluster_health.json")
    with open(health_path, "w") as f:
        json.dump(health, f, indent=2)

    entries_path = os.path.join(OUTPUT_DIR, "committed_entries.json")
    with open(entries_path, "w") as f:
        json.dump(committed, f, indent=2)

    print(f"Cluster health report: {health_path}")
    print(f"Committed entries manifest: {entries_path}")
    print(f"Active voters: {health['active_voters']}")
    print(f"Election timeout: {health['election_timeout_ms']}ms")
    print(f"Committed entries: {health['committed_count']}")


if __name__ == "__main__":
    main()
