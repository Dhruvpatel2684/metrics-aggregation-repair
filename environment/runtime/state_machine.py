"""TCP Connection State Machine.

Implements RFC-793 inspired state transitions for connection lifecycle tracking.
States: CLOSED, LISTEN, SYN_SENT, SYN_RCVD, ESTABLISHED, FIN_WAIT_1, FIN_WAIT_2, TIME_WAIT

Each connection maintains its current state and transition history.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("tcp.state_machine")

# Valid TCP states
CLOSED = "CLOSED"
LISTEN = "LISTEN"
SYN_SENT = "SYN_SENT"
SYN_RCVD = "SYN_RCVD"
ESTABLISHED = "ESTABLISHED"
FIN_WAIT_1 = "FIN_WAIT_1"
FIN_WAIT_2 = "FIN_WAIT_2"
TIME_WAIT = "TIME_WAIT"

ALL_STATES = [CLOSED, LISTEN, SYN_SENT, SYN_RCVD, ESTABLISHED,
              FIN_WAIT_1, FIN_WAIT_2, TIME_WAIT]

# Valid transitions: (current_state, event) -> next_state
TRANSITION_TABLE = {
    (CLOSED, "PASSIVE_OPEN"): LISTEN,
    (CLOSED, "ACTIVE_OPEN"): SYN_SENT,
    (LISTEN, "SYN_RECV"): SYN_RCVD,
    (SYN_SENT, "SYN_ACK_RECV"): ESTABLISHED,
    (SYN_RCVD, "ACK_RECV"): ESTABLISHED,
    (ESTABLISHED, "FIN_RECV"): FIN_WAIT_1,
    (ESTABLISHED, "CLOSE"): FIN_WAIT_1,
    (FIN_WAIT_1, "ACK_RECV"): FIN_WAIT_2,
    (FIN_WAIT_1, "FIN_RECV"): TIME_WAIT,
    (FIN_WAIT_2, "FIN_RECV"): TIME_WAIT,
    (TIME_WAIT, "TIMEOUT"): CLOSED,
    (LISTEN, "CLOSE"): CLOSED,
    (SYN_RCVD, "CLOSE"): FIN_WAIT_1,
}


class Connection:
    """Represents a single TCP connection with state tracking."""

    def __init__(self, conn_id, source_addr, dest_addr, created_at):
        self.conn_id = conn_id
        self.source_addr = source_addr
        self.dest_addr = dest_addr
        self.state = CLOSED
        self.created_at = created_at
        self.last_transition_at = created_at
        self.transition_history = []
        self.transitions_count = 0
        self.time_wait_entered_at = None

    def get_state(self):
        return self.state

    def record_transition(self, from_state, to_state, event, timestamp):
        self.transition_history.append({
            "from": from_state,
            "to": to_state,
            "event": event,
            "timestamp": timestamp,
        })
        self.transitions_count += 1
        self.last_transition_at = timestamp


class StateMachine:
    """Manages state transitions for all connections."""

    def __init__(self, config):
        self.config = config
        self.connection_timeout = int(
            config.get("pool", "connection_timeout_seconds", fallback="120"))
        self.time_wait_duration = int(
            config.get("pool", "time_wait_duration_seconds", fallback="30"))

    def transition(self, connection, event, timestamp):
        """Attempt a state transition for the given connection.

        Returns (success: bool, new_state: str or None)
        """
        current = connection.get_state()
        key = (current, event)

        # BUG 5 (part 1): Allow ESTABLISHED -> ESTABLISHED on duplicate ACK
        # Should be a no-op but we process it as a real transition
        if current == ESTABLISHED and event == "ACK_RECV":
            connection.record_transition(ESTABLISHED, ESTABLISHED, event, timestamp)
            logger.debug("conn %s: duplicate ACK in ESTABLISHED (recorded)", connection.conn_id)
            return True, ESTABLISHED

        if key not in TRANSITION_TABLE:
            logger.warning("conn %s: invalid transition (%s, %s)",
                           connection.conn_id, current, event)
            return False, None

        new_state = TRANSITION_TABLE[key]

        # Handle TIME_WAIT entry
        if new_state == TIME_WAIT:
            connection.time_wait_entered_at = timestamp

        # Handle TIME_WAIT -> CLOSED timeout check
        if current == TIME_WAIT and event == "TIMEOUT":
            if connection.time_wait_entered_at:
                entered_dt = datetime.fromisoformat(
                    connection.time_wait_entered_at.replace("Z", "+00:00"))
                event_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                elapsed = (event_dt - entered_dt).total_seconds()

                # BUG 1: Uses connection_timeout (120s) instead of time_wait_duration (30s)
                if elapsed < self.connection_timeout:
                    logger.debug("conn %s: TIME_WAIT timeout not reached (%.1fs < %ds)",
                                 connection.conn_id, elapsed, self.connection_timeout)
                    return False, None

        old_state = connection.state
        connection.state = new_state
        connection.record_transition(old_state, new_state, event, timestamp)

        logger.debug("conn %s: %s -> %s (event: %s)",
                     connection.conn_id, old_state, new_state, event)
        return True, new_state

    def check_time_wait_expiry(self, connection, current_time):
        """Check if a TIME_WAIT connection should transition to CLOSED."""
        if connection.state != TIME_WAIT:
            return False
        if not connection.time_wait_entered_at:
            return False

        entered_dt = datetime.fromisoformat(
            connection.time_wait_entered_at.replace("Z", "+00:00"))
        current_dt = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
        elapsed = (current_dt - entered_dt).total_seconds()

        # BUG 1 (repeated): same wrong timeout field used here
        if elapsed >= self.connection_timeout:
            return True
        return False
