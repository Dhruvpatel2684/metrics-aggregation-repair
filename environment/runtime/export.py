"""Connection State Export.

Exports final connection state and recovery report.
Produces:
- connection_state.jsonl: per-connection state records (sorted by conn_id)
- recovery_report.json: summary metadata, pool accounting, reconciliation stats
"""

import json
import hashlib
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("tcp.export")


def export_connection_state(connections, pool, handler_stats, event_stats,
                            reconciler_stats, output_dir):
    """Export connection states and recovery report."""
    os.makedirs(output_dir, exist_ok=True)

    state_path = os.path.join(output_dir, "connection_state.jsonl")
    report_path = os.path.join(output_dir, "recovery_report.json")

    hasher = hashlib.sha256()
    record_count = 0
    state_counts = {}

    with open(state_path, "w") as f:
        for conn_id in sorted(connections.keys()):
            conn = connections[conn_id]
            record = {
                "conn_id": conn.conn_id,
                "source_addr": conn.source_addr,
                "dest_addr": conn.dest_addr,
                "state": conn.state,
                "created_at": conn.created_at,
                "last_transition_at": conn.last_transition_at,
                "transitions_count": conn.transitions_count,
                "transition_history": conn.transition_history,
            }

            line = json.dumps(record, separators=(",", ":"), sort_keys=True)
            f.write(line + "\n")
            hasher.update(line.encode("utf-8"))
            record_count += 1

            state = conn.state
            state_counts[state] = state_counts.get(state, 0) + 1

    pool_state = pool.get_pool_state()

    report = {
        "sha256": hasher.hexdigest(),
        "record_count": record_count,
        "state_distribution": state_counts,
        "pool": pool_state,
        "pool_slot_history": pool.slot_history,
        "eviction_log": pool.eviction_log,
        "handler_stats": handler_stats,
        "event_stats": event_stats,
        "reconciler_stats": reconciler_stats,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("exported %d connection records -> %s", record_count, state_path)
    return state_path, report_path
