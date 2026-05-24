"""Connection Pool Manager.

Manages a fixed pool of connection slots. Tracks active connections,
handles slot allocation and release, and enforces connection limits.

Pool invariants:
- active_count must never exceed max_connections
- active_count must never go negative
- Each connection occupies exactly one slot
- Slots are released only when connection reaches CLOSED state
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("tcp.pool")


class PoolEntry:
    """Metadata for a connection's slot in the pool."""

    def __init__(self, conn_id, allocated_at):
        self.conn_id = conn_id
        self.allocated_at = allocated_at
        self.released = False
        self.release_reason = None
        self.transitions_count = 0


class ConnectionPool:
    """Fixed-size connection pool with slot management."""

    def __init__(self, config):
        self.max_connections = int(
            config.get("pool", "max_connections", fallback="10"))
        self.max_transitions = int(
            config.get("pool", "max_transitions_per_connection", fallback="8"))
        self.active_count = 0
        self.entries = {}
        self.slot_history = []
        self.eviction_log = []

    def allocate_slot(self, conn_id, timestamp):
        """Allocate a pool slot for a new connection."""
        if self.active_count >= self.max_connections:
            logger.warning("pool full: cannot allocate slot for %s", conn_id)
            return False

        # Create new pool entry for this connection
        entry = PoolEntry(conn_id, timestamp)
        self.entries[conn_id] = entry
        self.active_count += 1

        self.slot_history.append({
            "action": "allocate",
            "conn_id": conn_id,
            "timestamp": timestamp,
            "active_after": self.active_count,
        })
        return True

    def release_slot(self, conn_id, connection_state, reason="normal"):
        """Release a pool slot when connection is closing."""
        if conn_id not in self.entries:
            return False

        entry = self.entries[conn_id]
        if entry.released:
            return False

        # Release slot when connection enters a closing phase
        closing_states = ["FIN_WAIT_1", "FIN_WAIT_2", "TIME_WAIT", "CLOSED"]
        if connection_state in closing_states:
            entry.released = True
            entry.release_reason = reason
            self.active_count -= 1

            self.slot_history.append({
                "action": "release",
                "conn_id": conn_id,
                "state_at_release": connection_state,
                "reason": reason,
                "active_after": self.active_count,
            })
            return True

        return False

    def check_forced_eviction(self, conn_id, transitions_count):
        """Force-evict a connection that has exceeded max transitions."""
        if transitions_count > self.max_transitions:
            if conn_id in self.entries:
                entry = self.entries[conn_id]
                if not entry.released:
                    entry.released = True
                    entry.release_reason = "forced_eviction"
                    self.active_count -= 1
                    self.eviction_log.append({
                        "conn_id": conn_id,
                        "transitions": transitions_count,
                        "max_allowed": self.max_transitions,
                    })
                    return True
        return False

    def get_active_connections(self):
        return [cid for cid, entry in self.entries.items() if not entry.released]

    def get_pool_state(self):
        return {
            "max_connections": self.max_connections,
            "active_count": self.active_count,
            "total_allocated": len(self.entries),
            "released": sum(1 for e in self.entries.values() if e.released),
            "evictions": len(self.eviction_log),
        }
