"""
TCP-like connection state machine with defined transitions.
Each transition is a tuple of (current_state, event_type, direction) -> next_state.
"""

TRANSITIONS = {
    ("CLOSED", "ACTIVE_OPEN", "local"): "SYN_SENT",
    ("CLOSED", "PASSIVE_OPEN", "local"): "LISTEN",
    ("LISTEN", "SYN_RECV", "remote"): "SYN_RCVD",
    ("LISTEN", "CLOSE", "local"): "CLOSED",
    ("SYN_SENT", "SYN_ACK_RECV", "remote"): "ESTABLISHED",
    ("SYN_SENT", "CLOSE", "local"): "CLOSED",
    ("SYN_RCVD", "ACK_RECV", "remote"): "ESTABLISHED",
    ("SYN_RCVD", "CLOSE", "local"): "FIN_WAIT_1",
    ("ESTABLISHED", "FIN_SENT", "local"): "FIN_WAIT_1",
    ("ESTABLISHED", "FIN_RECV", "remote"): "CLOSE_WAIT",
    ("ESTABLISHED", "CLOSE", "local"): "FIN_WAIT_1",
    ("FIN_WAIT_1", "ACK_RECV", "remote"): "FIN_WAIT_2",
    ("FIN_WAIT_1", "FIN_RECV", "remote"): "CLOSING",
    ("FIN_WAIT_2", "FIN_RECV", "remote"): "TIME_WAIT",
    ("CLOSING", "ACK_RECV", "remote"): "TIME_WAIT",
    # TIME_WAIT expiry is handled by the event processor's elapsed time check
    # rather than as a simple state transition, since it requires timeout validation
    ("CLOSE_WAIT", "FIN_SENT", "local"): "LAST_ACK",
    ("LAST_ACK", "ACK_RECV", "remote"): "CLOSED",
}


def get_next_state(current_state, event_type, direction):
    """Look up the next state given current state, event type, and direction."""
    key = (current_state, event_type, direction)
    return TRANSITIONS.get(key)
