"""Election timeout management for Raft consensus protocol."""

import configparser
import os
from datetime import datetime, timezone


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")


def load_timing_config():
    """Load timing parameters from cluster configuration."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    timeout_ms = config.getint("timing", "election_timeout_ms")
    heartbeat_ms = config.getint("timing", "heartbeat_interval_ms")
    return {"election_timeout_ms": timeout_ms, "heartbeat_interval_ms": heartbeat_ms}


def get_election_timeout():
    """Return the configured election timeout in milliseconds."""
    timing = load_timing_config()
    return timing["election_timeout_ms"]


def validate_election_timing(events):
    """Validate that election events respect timeout constraints.

    Returns a dict with timing validation results.
    """
    timeout_ms = get_election_timeout()

    election_events = [e for e in events if e.get("type") == "election"]
    if not election_events:
        return {"valid": True, "timeout_ms": timeout_ms, "violations": 0}

    # Sort by timestamp to check intervals
    sorted_events = sorted(election_events, key=lambda e: e["timestamp"])

    violations = 0
    for i in range(1, len(sorted_events)):
        prev_ts = datetime.fromisoformat(sorted_events[i-1]["timestamp"].replace("Z", "+00:00"))
        curr_ts = datetime.fromisoformat(sorted_events[i]["timestamp"].replace("Z", "+00:00"))
        delta_ms = (curr_ts - prev_ts).total_seconds() * 1000

        if delta_ms > 0 and delta_ms < timeout_ms:
            violations += 1

    return {
        "valid": violations == 0,
        "timeout_ms": timeout_ms,
        "violations": violations,
        "events_checked": len(sorted_events)
    }
