"""
Reconciler: validates batch processing results, computes aggregate statistics,
and produces the final recovery report.
"""

import configparser


class Reconciler:
    """Reconciles batch snapshots into a final consistent view."""

    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.extended_timeout = self.config.getint(
            "pool.extended", "reservation_timeout_seconds"
        )

    def reconcile(self, connections, batch_snapshots, pool):
        """
        Produce the final reconciliation report.
        Validates state consistency and computes statistics.
        """
        report = {
            "total_connections": len(connections),
            "final_states": {},
            "transition_counts": {},
            "pool_status": {},
            "anomalies": [],
        }

        transition_totals = self._compute_transition_totals(
            connections, batch_snapshots
        )

        for conn_id, conn in connections.items():
            report["final_states"][conn_id] = conn.state
            report["transition_counts"][conn_id] = transition_totals.get(
                conn_id, conn.transitions_count
            )

        report["pool_status"] = {
            "active_slots": pool.active_count(),
            "total_tracked": len(pool.entries),
            "leaked_reservations": self._find_leaked_reservations(
                connections, pool
            ),
        }

        report["anomalies"] = self._detect_anomalies(connections, pool)
        return report

    def _compute_transition_totals(self, connections, batch_snapshots):
        """
        Compute total transitions for each connection across all batches.
        Accumulates transition counts from batch snapshots for connections
        that appear across multiple processing batches.
        """
        totals = {}
        for snapshot in batch_snapshots:
            for conn_id, data in snapshot.items():
                if conn_id not in totals:
                    totals[conn_id] = 0
                totals[conn_id] += data["transitions_count"]
        return totals

    def _find_leaked_reservations(self, connections, pool):
        """Find pool entries that are reserved but connection is in terminal state."""
        leaked = []
        for conn_id, entry in pool.entries.items():
            if entry.state == "RESERVED" and not entry.confirmed:
                if conn_id in connections:
                    conn = connections[conn_id]
                    if conn.state in ("CLOSED", "TIME_WAIT"):
                        leaked.append(conn_id)
        return leaked

    def _detect_anomalies(self, connections, pool):
        """Detect processing anomalies that indicate recovery issues."""
        anomalies = []

        for conn_id, conn in connections.items():
            if conn.state == "ESTABLISHED" and conn_id in pool.entries:
                entry = pool.entries[conn_id]
                if not entry.confirmed:
                    anomalies.append({
                        "type": "unconfirmed_established",
                        "conn_id": conn_id,
                        "detail": "Connection reached ESTABLISHED but pool slot not confirmed",
                    })

            if conn.state == "CLOSED" and conn_id in pool.entries:
                entry = pool.entries[conn_id]
                if not entry.confirmed:
                    anomalies.append({
                        "type": "unconfirmed_closed",
                        "conn_id": conn_id,
                        "detail": "Connection completed lifecycle without pool confirmation",
                    })

            if conn.state == "TIME_WAIT":
                anomalies.append({
                    "type": "stuck_time_wait",
                    "conn_id": conn_id,
                    "detail": "Connection stuck in TIME_WAIT after timeout event",
                })

            if conn.state in ("LISTEN", "SYN_RCVD") and conn.transitions_count > 0:
                expected_transitions = len([
                    h for h in conn.transition_history
                    if h["to"] not in ("LISTEN", "SYN_RCVD")
                ])
                if expected_transitions == 0 and conn.transitions_count >= 2:
                    anomalies.append({
                        "type": "stalled_handshake",
                        "conn_id": conn_id,
                        "detail": f"Connection stalled in {conn.state} despite receiving events",
                    })

        return anomalies
