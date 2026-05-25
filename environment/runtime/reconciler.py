"""Connection State Reconciler.

Merges results from batch processing passes, sweeps stale reservations,
deduplicates cross-source events, and reconciles transition counts.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("tcp.reconciler")


class Reconciler:
    """Reconciles connection states across processing batches."""

    def __init__(self, config, pool):
        self.config = config
        self.pool = pool
        self.reconciliation_window_ms = int(
            config.get("reconciler", "reconciliation_window_ms", fallback="50"))
        self.reservation_timeout = int(
            config.get("pool", "reservation_timeout_seconds", fallback="5"))

        self.batch_results = []
        self.reconciled_connections = {}
        self.sweep_log = []

    def add_batch_result(self, connections_snapshot):
        """Record the state of connections after a batch is processed."""
        batch_state = {}
        for conn_id, conn in connections_snapshot.items():
            batch_state[conn_id] = {
                "state": conn.state,
                "transitions_count": conn.transitions_count,
                "last_transition_at": conn.last_transition_at,
            }
        self.batch_results.append(batch_state)

    def reconcile_transitions(self, connections):
        """Reconcile transition counts across batches.

        Accumulates transition counts from all batch snapshots to produce
        the final count for each connection.
        """
        conn_total_transitions = {}

        for batch_state in self.batch_results:
            for conn_id, state_info in batch_state.items():
                if conn_id not in conn_total_transitions:
                    conn_total_transitions[conn_id] = 0
                # Sum transitions across all batch appearances
                conn_total_transitions[conn_id] += state_info["transitions_count"]

        # Update connection objects with reconciled counts
        for conn_id, total in conn_total_transitions.items():
            if conn_id in connections:
                connections[conn_id].transitions_count = total

        return conn_total_transitions

    def sweep_stale_reservations(self, connections, current_time):
        """Sweep pool reservations that were never confirmed."""
        current_dt = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
        swept = []

        for conn_id, entry in list(self.pool.entries.items()):
            if entry.status != "reserved":
                continue

            # Check if reservation has exceeded timeout
            activity_dt = datetime.fromisoformat(
                entry.last_activity_at.replace("Z", "+00:00"))
            elapsed = (current_dt - activity_dt).total_seconds()

            if elapsed > self.reservation_timeout:
                entry.released = True
                entry.release_reason = "stale_reservation"
                entry.status = "released"
                self.pool.reserved_count -= 1

                self.sweep_log.append({
                    "conn_id": conn_id,
                    "elapsed": elapsed,
                    "threshold": self.reservation_timeout,
                })
                swept.append(conn_id)

                if conn_id in connections:
                    connections[conn_id].state = "CLOSED"

        if swept:
            logger.info("swept %d stale reservations: %s", len(swept), swept)

        return swept

    def deduplicate_cross_source(self, connections):
        """Remove duplicate events from multiple sources within reconciliation window."""
        for conn_id, conn in connections.items():
            if len(conn.transition_history) < 2:
                continue

            deduped_history = [conn.transition_history[0]]
            for i in range(1, len(conn.transition_history)):
                prev = deduped_history[-1]
                curr = conn.transition_history[i]

                # Check if this is a duplicate from another source
                if (prev["event"] == curr["event"] and
                        prev["from"] == curr["from"] and
                        prev["to"] == curr["to"]):
                    delta = abs(self._timestamp_delta_ms(
                        prev["timestamp"], curr["timestamp"]))
                    if delta <= self.reconciliation_window_ms:
                        continue  # Skip duplicate

                deduped_history.append(curr)

            conn.transition_history = deduped_history

    def _timestamp_delta_ms(self, ts_a, ts_b):
        """Compute millisecond delta between two timestamps."""
        # Approximate comparison using string ordering
        if ts_a > ts_b:
            return 1000
        elif ts_a < ts_b:
            return -1000
        else:
            return 0

    def reconcile(self, connections, current_time):
        """Run full reconciliation pass."""
        # Sweep stale reservations
        self.sweep_stale_reservations(connections, current_time)

        # Deduplicate cross-source events
        self.deduplicate_cross_source(connections)

        # Reconcile transition counts (accumulate across batches)
        self.reconcile_transitions(connections)

        self.reconciled_connections = connections
        return connections

    def get_reconciler_stats(self):
        return {
            "batches_processed": len(self.batch_results),
            "stale_swept": len(self.sweep_log),
            "reconciled_connections": len(self.reconciled_connections),
        }
