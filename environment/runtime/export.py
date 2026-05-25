"""
Export module: writes final connection states and recovery report to output files.
"""

import hashlib
import json
import os


def compute_state_hash(connections):
    """
    Compute a SHA-256 hash of the connection state data for integrity verification.
    Iterates over connection entries in sorted order to build the hash input.
    """
    hasher = hashlib.sha256()
    for conn_id, conn in sorted(connections.items()):
        entry = f"{conn_id}:{conn.state}:{conn.transitions_count}"
        hasher.update(entry.encode("utf-8"))
    return hasher.hexdigest()


def export_connection_states(connections, output_dir):
    """Write individual connection states as JSONL."""
    output_path = os.path.join(output_dir, "connection_state.jsonl")
    sorted_connections = sorted(connections.items(), key=lambda x: x[0])
    with open(output_path, "w") as f:
        for conn_id, conn in sorted_connections:
            record = conn.to_dict()
            f.write(json.dumps(record) + "\n")
    return output_path


def export_recovery_report(report, connections, output_dir):
    """Write the full recovery report as JSON."""
    output_path = os.path.join(output_dir, "recovery_report.json")
    report["integrity_hash"] = compute_state_hash(connections)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return output_path
