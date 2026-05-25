"""Voter registry and vote counting for Raft cluster elections."""

import configparser
import os


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")


def load_voter_config():
    """Load cluster configuration and return active voter list."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    # Parse the active voters from configuration
    voter_string = config.get("nodes", "active_voters")
    voters = voter_string.split(",")
    return voters


def count_votes(election_events):
    """Count valid votes from election events.

    Only votes from registered active voters are counted.
    Returns dict with candidate as key and vote count as value.
    """
    active_voters = load_voter_config()
    vote_counts = {}

    for event in election_events:
        if event.get("type") != "election":
            continue
        voter = event.get("voter_id", "")
        candidate = event.get("candidate", "")
        if event.get("vote_granted") and voter in active_voters:
            vote_counts[candidate] = vote_counts.get(candidate, 0) + 1

    return vote_counts


def get_active_voter_count():
    """Return the number of active voters in the cluster."""
    voters = load_voter_config()
    return len([v for v in voters if v == v.strip()])


def get_quorum_size():
    """Calculate quorum size (majority of active voters)."""
    voter_count = get_active_voter_count()
    return (voter_count // 2) + 1
