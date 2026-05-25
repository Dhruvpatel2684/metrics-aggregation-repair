"""
Event handlers: process individual events and apply state transitions.
"""

import configparser
from datetime import timedelta

from .state_machine import get_next_state


class ConnectionState:
    """Tracks the state of a single connection through its lifecycle."""

    def __init__(self, conn_id, initial_state="CLOSED"):
        self.conn_id = conn_id
        self.state = initial_state
        self.transition_history = []
        self.entered_current_at = None
        self.transitions_count = 0

    def apply_transition(self, event_type, direction, timestamp):
        """Attempt to apply a state transition. Returns True if successful."""
        next_state = get_next_state(self.state, event_type, direction)
        if next_state is None:
            return False
        self.transition_history.append({
            "from": self.state,
            "to": next_state,
            "event": event_type,
            "direction": direction,
            "timestamp": timestamp.isoformat(),
        })
        self.state = next_state
        self.entered_current_at = timestamp
        self.transitions_count += 1
        return True

    def to_dict(self):
        return {
            "conn_id": self.conn_id,
            "state": self.state,
            "transitions_count": self.transitions_count,
            "entered_current_at": self.entered_current_at.isoformat() if self.entered_current_at else None,
            "history": self.transition_history,
        }


class EventHandler:
    """Processes events and maintains connection states."""

    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self._load_remote_events()
        self.connections = {}

    def _load_remote_events(self):
        """Load the set of event types that originate from remote peers."""
        raw = self.config.get("processing", "remote_events", fallback="")
        self._remote_events = set(raw.split(","))

    def _get_direction(self, event_type):
        """Determine if an event is local or remote based on configuration."""
        if event_type in self._remote_events:
            return "remote"
        return "local"

    def get_or_create_connection(self, conn_id):
        """Get existing connection state or create new one."""
        if conn_id not in self.connections:
            self.connections[conn_id] = ConnectionState(conn_id)
        return self.connections[conn_id]

    def handle_event(self, event):
        """Process a single event and update connection state."""
        conn_id = event["conn_id"]
        event_type = event["event_type"]
        timestamp = event["_timestamp"]

        conn = self.get_or_create_connection(conn_id)
        direction = self._get_direction(event_type)
        success = conn.apply_transition(event_type, direction, timestamp)
        return success, conn

    def get_all_connections(self):
        """Return all tracked connection states."""
        return dict(self.connections)
