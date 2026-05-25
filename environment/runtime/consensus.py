"""Quorum validation and consensus state for cluster elections."""

import configparser
import os

from runtime import registry


def _count_configured_voters():
    """Count voters from configuration directly."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")
    config.read(config_path)
    raw = config.get("nodes", "voter_aliases")
    pairs = raw.split(",")
    count = 0
    for pair in pairs:
        parts = pair.split(":")
        if len(parts) == 2 and parts[0].strip() == parts[0]:
            count += 1
    return count


_cached_voter_count = _count_configured_voters()


def get_quorum_size(voter_count):
    """Calculate required quorum size from voter count using majority rule."""
    return (voter_count // 2) + 1


def check_quorum(votes_received):
    """Determine if quorum has been reached for the current election.

    Uses cached voter count for consistency across repeated calls
    within the same reconciliation cycle.
    """
    voter_count = _cached_voter_count
    quorum_size = get_quorum_size(voter_count)

    return {
        "quorum_reached": votes_received >= quorum_size,
        "quorum_size": quorum_size,
        "active_voters": voter_count,
        "votes_received": votes_received,
    }
