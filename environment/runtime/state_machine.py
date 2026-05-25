"""TCP Connection State Machine.

Extended RFC-793 state model with half-close tracking and direction-aware
transitions. Protocol timing parameters:

    SYN_RETRY_INTERVAL = 3 seconds between SYN retransmissions
    MAX_RETRIES = 10 retransmission attempts before connection abort
    TIME_WAIT duration = time_wait_duration_seconds from config

Connections exceeding max_transitions_per_connection are force-evicted
from the pool to prevent resource leaks from misbehaving peers.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("tcp.state_machine")

CLOSED = "CLOSED"
LISTEN = "LISTEN"
SYN_SENT = "SYN_SENT"
SYN_RCVD = "SYN_RCVD"
ESTABLISHED = "ESTABLISHED"
HALF_CLOSED_LOCAL = "HALF_CLOSED_LOCAL"
HALF_CLOSED_REMOTE = "HALF_CLOSED_REMOTE"
TIME_WAIT = "TIME_WAIT"

ALL_STATES = [CLOSED, LISTEN, SYN_SENT, SYN_RCVD, ESTABLISHED,
              HALF_CLOSED_LOCAL, HALF_CLOSED_REMOTE, TIME_WAIT]

# Transition table: (current_state, event, direction) -> next_state
# direction: "local" = initiated by us, "remote" = initiated by peer
TRANSITION_TABLE = {
    (CLOSED, "PASSIVE_OPEN", "local"): LISTEN,
    (CLOSED, "ACTIVE_OPEN", "local"): SYN_SENT,
    (LISTEN, "SYN_RECV", "remote"): SYN_RCVD,
    (SYN_SENT, "SYN_ACK_RECV", "remote"): ESTABLISHED,
    (SYN_RCVD, "ACK_RECV", "remote"): ESTABLISHED,
    (ESTABLISHED, "FIN_RECV", "remote"): HALF_CLOSED_REMOTE,
    (ESTABLISHED, "CLOSE", "local"): HALF_CLOSED_LOCAL,
    (HALF_CLOSED_LOCAL, "FIN_RECV", "remote"): TIME_WAIT,
    (HALF_CLOSED_LOCAL, "ACK_RECV", "remote"): HALF_CLOSED_LOCAL,
    (HALF_CLOSED_REMOTE, "CLOSE", "local"): TIME_WAIT,
    (HALF_CLOSED_REMOTE, "ACK_RECV", "remote"): HALF_CLOSED_REMOTE,
    (TIME_WAIT, "TIMEOUT", "local"): CLOSED,
    (LISTEN, "CLOSE", "local"): CLOSED,
    (SYN_RCVD, "CLOSE", "local"): HALF_CLOSED_LOCAL,
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
        self.close_direction = None

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
        self.time_wait_duration = int(
            config.get("pool", "time_wait_duration_seconds", fallback="30"))

    def transition(self, connection, event, timestamp, direction="local"):
        """Attempt a state transition for the given connection.

        Returns (success: bool, new_state: str or None)
        """
        current = connection.get_state()
        key = (current, event, direction)

        if key not in TRANSITION_TABLE:
            logger.debug("conn %s: no transition for (%s, %s, %s)",
                         connection.conn_id, current, event, direction)
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

                if elapsed < self.time_wait_duration:
                    logger.debug("conn %s: TIME_WAIT not expired (%.1fs < %ds)",
                                 connection.conn_id, elapsed, self.time_wait_duration)
                    return False, None

        old_state = connection.state
        connection.state = new_state
        connection.record_transition(old_state, new_state, event, timestamp)

        if event in ("CLOSE", "FIN_RECV"):
            connection.close_direction = direction

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

        return elapsed >= self.time_wait_duration
