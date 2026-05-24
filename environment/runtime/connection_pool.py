"""Connection Pool Manager.

Two-phase slot management: RESERVED on SYN_RECV, CONFIRMED on ESTABLISHED.
Reservations that are not confirmed within reservation_timeout_seconds are
considered stale and eligible for sweep.

Pool invariants:
- (reserved + confirmed) must never exceed max_connections
- active_count must never go negative
- Each connection occupies exactly one slot (reserved OR confirmed)
- Slots are released only when connection reaches CLOSED state
- Forced eviction applies to connections exceeding max_transitions
"""

import logging

logger = logging.getLogger("tcp.pool")


class PoolEntry:
    """Metadata for a connection's slot in the pool."""

    def __init__(self, conn_id, reserved_at):
        self.conn_id = conn_id
        self.reserved_at = reserved_at
        self.confirmed_at = None
        self.last_activity_at = reserved_at
        self.released = False
        self.release_reason = None
        self.status = "reserved"  # "reserved", "confirmed", "released"


class ConnectionPool:
    """Fixed-size connection pool with two-phase slot management."""

    def __init__(self, config):
        self.max_connections = int(
            config.get("pool", "max_connections", fallback="12"))
        self.max_transitions = int(
            config.get("pool", "max_transitions_per_connection", fallback="10"))
        self.reservation_timeout = int(
            config.get("pool", "reservation_timeout_seconds", fallback="5"))
        self.reserved_count = 0
        self.confirmed_count = 0
        self.entries = {}
        self.slot_history = []
        self.eviction_log = []

    @property
    def active_count(self):
        """Total active slots (reserved + confirmed)."""
        return self.reserved_count + self.confirmed_count

    def reserve_slot(self, conn_id, timestamp):
        """Reserve a pool slot for a new connection (phase 1)."""
        if self.active_count >= self.max_connections:
            logger.warning("pool full: cannot reserve slot for %s (active=%d)",
                           conn_id, self.active_count)
            return False

        entry = PoolEntry(conn_id, timestamp)
        self.entries[conn_id] = entry
        self.reserved_count += 1

        self.slot_history.append({
            "action": "reserve",
            "conn_id": conn_id,
            "timestamp": timestamp,
            "active_after": self.active_count,
        })
        return True

    def confirm_slot(self, conn_id, timestamp):
        """Confirm a reserved slot when connection reaches ESTABLISHED (phase 2)."""
        if conn_id not in self.entries:
            return False

        entry = self.entries[conn_id]
        if entry.status != "reserved":
            return False

        entry.status = "confirmed"
        entry.confirmed_at = timestamp
        entry.last_activity_at = timestamp
        self.reserved_count -= 1
        self.confirmed_count += 1

        self.slot_history.append({
            "action": "confirm",
            "conn_id": conn_id,
            "timestamp": timestamp,
            "active_after": self.active_count,
        })
        return True

    def release_slot(self, conn_id, connection_state, reason="normal"):
        """Release a pool slot when connection reaches CLOSED."""
        if conn_id not in self.entries:
            return False

        entry = self.entries[conn_id]
        if entry.released:
            return False

        if connection_state != "CLOSED":
            return False

        old_status = entry.status
        entry.released = True
        entry.release_reason = reason
        entry.status = "released"

        if old_status == "reserved":
            self.reserved_count -= 1
        elif old_status == "confirmed":
            self.confirmed_count -= 1

        self.slot_history.append({
            "action": "release",
            "conn_id": conn_id,
            "state_at_release": connection_state,
            "reason": reason,
            "active_after": self.active_count,
        })
        return True

    def update_activity(self, conn_id, timestamp):
        """Update last activity timestamp for a connection."""
        if conn_id in self.entries:
            self.entries[conn_id].last_activity_at = timestamp

    def check_forced_eviction(self, conn_id, transitions_count):
        """Force-evict a connection that has exceeded max transitions."""
        if transitions_count > self.max_transitions:
            if conn_id in self.entries:
                entry = self.entries[conn_id]
                if not entry.released:
                    old_status = entry.status
                    entry.released = True
                    entry.release_reason = "forced_eviction"
                    entry.status = "released"

                    if old_status == "reserved":
                        self.reserved_count -= 1
                    elif old_status == "confirmed":
                        self.confirmed_count -= 1

                    self.eviction_log.append({
                        "conn_id": conn_id,
                        "transitions": transitions_count,
                        "max_allowed": self.max_transitions,
                    })
                    return True
        return False

    def get_pool_state(self):
        """Return current pool state summary."""
        return {
            "max_connections": self.max_connections,
            "active_count": self.active_count,
            "reserved_count": self.reserved_count,
            "confirmed_count": self.confirmed_count,
            "total_allocated": len(self.entries),
            "released": sum(1 for e in self.entries.values() if e.released),
            "evictions": len(self.eviction_log),
        }
