"""
Connection pool manager: tracks active connection slots, reservations,
and enforces capacity limits.
"""

from datetime import datetime


class PoolEntry:
    """Represents a single connection slot in the pool."""

    def __init__(self, conn_id, reserved_at):
        self.conn_id = conn_id
        self.reserved_at = reserved_at
        self.last_activity_at = reserved_at
        self.confirmed = False
        self.state = "RESERVED"

    def confirm(self):
        """Mark this reservation as confirmed (handshake complete)."""
        self.confirmed = True
        self.state = "ACTIVE"

    def update_activity(self, timestamp):
        """Update the last activity timestamp."""
        self.last_activity_at = timestamp

    def release(self):
        """Release this slot back to the pool."""
        self.state = "RELEASED"

    def to_dict(self):
        return {
            "conn_id": self.conn_id,
            "reserved_at": self.reserved_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
            "confirmed": self.confirmed,
            "state": self.state,
        }


class ConnectionPool:
    """Manages connection slots with reservation semantics."""

    def __init__(self, max_connections, reservation_timeout):
        self.max_connections = max_connections
        self.reservation_timeout = reservation_timeout
        self.entries = {}

    def reserve(self, conn_id, timestamp):
        """Reserve a slot for a new connection."""
        if conn_id in self.entries:
            return True
        if self.active_count() >= self.max_connections:
            return False
        self.entries[conn_id] = PoolEntry(conn_id, timestamp)
        return True

    def confirm(self, conn_id, timestamp):
        """Confirm a reservation (connection established)."""
        if conn_id in self.entries and self.entries[conn_id].state == "RESERVED":
            self.entries[conn_id].confirm()
            self.entries[conn_id].update_activity(timestamp)
            return True
        return False

    def release(self, conn_id):
        """Release a connection slot."""
        if conn_id in self.entries:
            self.entries[conn_id].release()
            return True
        return False

    def update_activity(self, conn_id, timestamp):
        """Update activity timestamp for a connection."""
        if conn_id in self.entries:
            self.entries[conn_id].update_activity(timestamp)

    def active_count(self):
        """Count of slots that are reserved or active (not released)."""
        return sum(1 for e in self.entries.values() if e.state != "RELEASED")

    def sweep_stale(self, current_time):
        """Remove reservations that have exceeded the timeout without confirmation."""
        stale = []
        for conn_id, entry in self.entries.items():
            if not entry.confirmed and entry.state == "RESERVED":
                elapsed = (current_time - entry.last_activity_at).total_seconds()
                if elapsed > self.reservation_timeout:
                    stale.append(conn_id)
        for conn_id in stale:
            self.entries[conn_id].release()
        return stale

    def get_snapshot(self):
        """Return a snapshot of current pool state."""
        return {
            conn_id: entry.to_dict()
            for conn_id, entry in self.entries.items()
            if entry.state != "RELEASED"
        }
