"""Connection Event Handlers.

Dispatches events to the state machine with appropriate direction flags.
Manages connection creation, state transitions, and pool interactions.
"""

import logging

from runtime.state_machine import (
    Connection, StateMachine, CLOSED, LISTEN, SYN_RCVD,
    ESTABLISHED, HALF_CLOSED_LOCAL, HALF_CLOSED_REMOTE, TIME_WAIT
)
from runtime.connection_pool import ConnectionPool

logger = logging.getLogger("tcp.handlers")

LOCAL_EVENTS = {"PASSIVE_OPEN", "ACTIVE_OPEN", "CLOSE", "TIMEOUT"}
REMOTE_EVENTS = {"SYN_RECV", "SYN_ACK_RECV", "ACK_RECV", "FIN_RECV"}


class ConnectionHandlers:
    """Handles TCP connection events and coordinates state/pool interactions."""

    def __init__(self, state_machine, pool):
        self.state_machine = state_machine
        self.pool = pool
        self.connections = {}
        self.handler_log = []

    def handle_event(self, event):
        """Dispatch an event to the appropriate handler."""
        event_type = event.get("event_type")
        conn_id = event.get("conn_id")
        timestamp = event.get("timestamp")
        source_addr = event.get("source_addr", "0.0.0.0:0")
        dest_addr = event.get("dest_addr", "0.0.0.0:0")

        result = {"conn_id": conn_id, "event_type": event_type,
                  "timestamp": timestamp, "handled": False, "action": None}

        if event_type in ("PASSIVE_OPEN", "ACTIVE_OPEN"):
            result = self._handle_open(conn_id, source_addr, dest_addr,
                                       timestamp, event_type)
        elif event_type == "SYN_RECV":
            result = self._handle_syn_recv(conn_id, source_addr, dest_addr, timestamp)
        elif event_type == "ACK_RECV":
            result = self._handle_ack(conn_id, timestamp)
        elif event_type == "FIN_RECV":
            result = self._handle_transition(conn_id, "FIN_RECV", timestamp)
        elif event_type == "CLOSE":
            result = self._handle_close(conn_id, timestamp)
        elif event_type == "TIMEOUT":
            result = self._handle_timeout(conn_id, timestamp)
        elif event_type == "SYN_ACK_RECV":
            result = self._handle_transition(conn_id, "SYN_ACK_RECV", timestamp)
        else:
            result["action"] = "unknown_event"

        self.handler_log.append(result)
        return result

    def _handle_open(self, conn_id, source_addr, dest_addr, timestamp, open_type):
        """Handle PASSIVE_OPEN or ACTIVE_OPEN."""
        result = {"conn_id": conn_id, "event_type": open_type,
                  "timestamp": timestamp, "handled": False, "action": None}

        conn = Connection(conn_id, source_addr, dest_addr, timestamp)
        self.connections[conn_id] = conn

        success, new_state = self.state_machine.transition(
            conn, open_type, timestamp, direction="local")
        if success:
            result["handled"] = True
            result["action"] = f"opened_{new_state}"
        else:
            result["action"] = "transition_failed"
        return result

    def _handle_syn_recv(self, conn_id, source_addr, dest_addr, timestamp):
        """Handle SYN_RECV — reserve pool slot and transition."""
        result = {"conn_id": conn_id, "event_type": "SYN_RECV",
                  "timestamp": timestamp, "handled": False, "action": None}

        if conn_id not in self.connections:
            conn = Connection(conn_id, source_addr, dest_addr, timestamp)
            conn.state = LISTEN
            self.connections[conn_id] = conn

        conn = self.connections[conn_id]

        # Reserve a pool slot — no dedup check for retransmits
        self.pool.reserve_slot(conn_id, timestamp)

        success, new_state = self.state_machine.transition(
            conn, "SYN_RECV", timestamp, direction="remote")
        if success:
            result["handled"] = True
            result["action"] = f"syn_rcvd_{new_state}"
        else:
            result["action"] = "syn_recv_failed"

        self.pool.update_activity(conn_id, timestamp)
        return result

    def _handle_ack(self, conn_id, timestamp):
        """Handle ACK_RECV — confirm slot if transitioning to ESTABLISHED."""
        result = {"conn_id": conn_id, "event_type": "ACK_RECV",
                  "timestamp": timestamp, "handled": False, "action": None}

        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result

        conn = self.connections[conn_id]
        old_state = conn.state

        success, new_state = self.state_machine.transition(
            conn, "ACK_RECV", timestamp, direction="remote")

        if success:
            result["handled"] = True
            result["action"] = f"ack_{new_state}"

            # Confirm pool slot when reaching ESTABLISHED
            if old_state == SYN_RCVD and new_state == ESTABLISHED:
                self.pool.confirm_slot(conn_id, timestamp)

            # Check forced eviction
            evicted = self.pool.check_forced_eviction(
                conn_id, conn.transitions_count)
            if evicted:
                result["action"] = "force_evicted"
        else:
            result["action"] = "ack_ignored"

        self.pool.update_activity(conn_id, timestamp)
        return result

    def _handle_transition(self, conn_id, event_type, timestamp):
        """Generic transition handler — used for FIN_RECV and SYN_ACK_RECV."""
        result = {"conn_id": conn_id, "event_type": event_type,
                  "timestamp": timestamp, "handled": False, "action": None}

        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result

        conn = self.connections[conn_id]

        # Use local direction for generic transitions
        success, new_state = self.state_machine.transition(
            conn, event_type, timestamp, direction="local")

        if success:
            result["handled"] = True
            result["action"] = f"transition_{new_state}"
        else:
            result["action"] = "transition_failed"

        self.pool.update_activity(conn_id, timestamp)
        return result

    def _handle_close(self, conn_id, timestamp):
        """Handle CLOSE — local-initiated close."""
        result = {"conn_id": conn_id, "event_type": "CLOSE",
                  "timestamp": timestamp, "handled": False, "action": None}

        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result

        conn = self.connections[conn_id]
        success, new_state = self.state_machine.transition(
            conn, "CLOSE", timestamp, direction="local")

        if success:
            result["handled"] = True
            result["action"] = f"close_{new_state}"
        else:
            result["action"] = "close_failed"

        self.pool.update_activity(conn_id, timestamp)
        return result

    def _handle_timeout(self, conn_id, timestamp):
        """Handle TIMEOUT — TIME_WAIT expiry."""
        result = {"conn_id": conn_id, "event_type": "TIMEOUT",
                  "timestamp": timestamp, "handled": False, "action": None}

        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result

        conn = self.connections[conn_id]
        success, new_state = self.state_machine.transition(
            conn, "TIMEOUT", timestamp, direction="local")

        if success:
            result["handled"] = True
            result["action"] = f"timeout_{new_state}"
            self.pool.release_slot(conn_id, new_state, reason="timeout_expiry")
        else:
            result["action"] = "timeout_not_ready"

        return result

    def get_all_connections(self):
        return self.connections

    def get_handler_stats(self):
        handled = sum(1 for r in self.handler_log if r.get("handled"))
        return {"total_events": len(self.handler_log), "handled": handled,
                "failed": len(self.handler_log) - handled}
