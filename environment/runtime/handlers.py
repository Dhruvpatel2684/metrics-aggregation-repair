"""Connection Event Handlers."""

import logging
from datetime import datetime, timezone

from runtime.state_machine import (
    Connection, StateMachine, CLOSED, LISTEN, SYN_RCVD,
    ESTABLISHED, FIN_WAIT_1, FIN_WAIT_2, TIME_WAIT
)
from runtime.connection_pool import ConnectionPool

logger = logging.getLogger("tcp.handlers")


class ConnectionHandlers:
    def __init__(self, state_machine, pool):
        self.state_machine = state_machine
        self.pool = pool
        self.connections = {}
        self.handler_log = []

    def handle_event(self, event):
        event_type = event.get("event_type")
        conn_id = event.get("conn_id")
        timestamp = event.get("timestamp")
        source_addr = event.get("source_addr", "0.0.0.0:0")
        dest_addr = event.get("dest_addr", "0.0.0.0:0")

        result = {"conn_id": conn_id, "event_type": event_type,
                  "timestamp": timestamp, "handled": False, "action": None}

        if event_type == "PASSIVE_OPEN":
            result = self._handle_open(conn_id, source_addr, dest_addr, timestamp, "PASSIVE_OPEN")
        elif event_type == "ACTIVE_OPEN":
            result = self._handle_open(conn_id, source_addr, dest_addr, timestamp, "ACTIVE_OPEN")
        elif event_type == "SYN_RECV":
            result = self._handle_syn_recv(conn_id, source_addr, dest_addr, timestamp)
        elif event_type == "SYN_ACK_RECV":
            result = self._handle_transition(conn_id, "SYN_ACK_RECV", timestamp)
        elif event_type == "ACK_RECV":
            result = self._handle_ack(conn_id, timestamp)
        elif event_type == "FIN_RECV":
            result = self._handle_fin(conn_id, timestamp)
        elif event_type == "CLOSE":
            result = self._handle_close(conn_id, timestamp)
        elif event_type == "TIMEOUT":
            result = self._handle_timeout(conn_id, timestamp)
        else:
            result["action"] = "unknown_event"

        self.handler_log.append(result)
        return result

    def _handle_open(self, conn_id, source_addr, dest_addr, timestamp, open_type):
        result = {"conn_id": conn_id, "event_type": open_type,
                  "timestamp": timestamp, "handled": False, "action": None}
        conn = Connection(conn_id, source_addr, dest_addr, timestamp)
        self.connections[conn_id] = conn
        allocated = self.pool.allocate_slot(conn_id, timestamp)
        if not allocated:
            result["action"] = "pool_full"
            return result
        success, new_state = self.state_machine.transition(conn, open_type, timestamp)
        if success:
            result["handled"] = True
            result["action"] = f"opened_{new_state}"
        else:
            result["action"] = "transition_failed"
        return result

    def _handle_syn_recv(self, conn_id, source_addr, dest_addr, timestamp):
        """Handle SYN_RECV — create connection if not yet tracked."""
        result = {"conn_id": conn_id, "event_type": "SYN_RECV",
                  "timestamp": timestamp, "handled": False, "action": None}
        if conn_id not in self.connections:
            conn = Connection(conn_id, source_addr, dest_addr, timestamp)
            conn.state = LISTEN
            self.connections[conn_id] = conn
            # Ensure connection has a pool slot allocated
            self.pool.allocate_slot(conn_id, timestamp)

        conn = self.connections[conn_id]
        success, new_state = self.state_machine.transition(conn, "SYN_RECV", timestamp)
        if success:
            result["handled"] = True
            result["action"] = f"syn_rcvd_{new_state}"
        else:
            result["action"] = "syn_recv_failed"
        return result

    def _handle_ack(self, conn_id, timestamp):
        result = {"conn_id": conn_id, "event_type": "ACK_RECV",
                  "timestamp": timestamp, "handled": False, "action": None}
        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result
        conn = self.connections[conn_id]
        success, new_state = self.state_machine.transition(conn, "ACK_RECV", timestamp)
        if success:
            result["handled"] = True
            result["action"] = f"ack_{new_state}"
            # Check connection health after ACK processing
            evicted = self.pool.check_forced_eviction(conn_id, conn.transitions_count)
            if evicted:
                result["action"] = "force_evicted"
        else:
            result["action"] = "ack_failed"
        return result

    def _handle_fin(self, conn_id, timestamp):
        result = {"conn_id": conn_id, "event_type": "FIN_RECV",
                  "timestamp": timestamp, "handled": False, "action": None}
        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result
        conn = self.connections[conn_id]
        success, new_state = self.state_machine.transition(conn, "FIN_RECV", timestamp)
        if success:
            result["handled"] = True
            result["action"] = f"fin_{new_state}"
            # Release pool slot as connection is closing down
            self.pool.release_slot(conn_id, new_state, reason="fin_received")
        else:
            result["action"] = "fin_failed"
        return result

    def _handle_close(self, conn_id, timestamp):
        result = {"conn_id": conn_id, "event_type": "CLOSE",
                  "timestamp": timestamp, "handled": False, "action": None}
        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result
        conn = self.connections[conn_id]
        success, new_state = self.state_machine.transition(conn, "CLOSE", timestamp)
        if success:
            result["handled"] = True
            result["action"] = f"close_{new_state}"
            # Release pool slot on close
            self.pool.release_slot(conn_id, new_state, reason="close_initiated")
        else:
            result["action"] = "close_failed"
        return result

    def _handle_timeout(self, conn_id, timestamp):
        result = {"conn_id": conn_id, "event_type": "TIMEOUT",
                  "timestamp": timestamp, "handled": False, "action": None}
        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result
        conn = self.connections[conn_id]
        success, new_state = self.state_machine.transition(conn, "TIMEOUT", timestamp)
        if success:
            result["handled"] = True
            result["action"] = f"timeout_{new_state}"
            self.pool.release_slot(conn_id, new_state, reason="timeout_expiry")
        else:
            result["action"] = "timeout_not_ready"
        return result

    def _handle_transition(self, conn_id, event_type, timestamp):
        result = {"conn_id": conn_id, "event_type": event_type,
                  "timestamp": timestamp, "handled": False, "action": None}
        if conn_id not in self.connections:
            result["action"] = "no_connection"
            return result
        conn = self.connections[conn_id]
        success, new_state = self.state_machine.transition(conn, event_type, timestamp)
        if success:
            result["handled"] = True
            result["action"] = f"transition_{new_state}"
        else:
            result["action"] = "transition_failed"
        return result

    def get_all_connections(self):
        return self.connections

    def get_handler_stats(self):
        handled = sum(1 for r in self.handler_log if r.get("handled"))
        return {"total_events": len(self.handler_log), "handled": handled,
                "failed": len(self.handler_log) - handled}
