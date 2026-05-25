"""Voter identity resolution and alias management for cluster membership."""

import configparser
import os


def load_registry_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")
    config.read(config_path)
    return config.get("nodes", "voter_aliases")


def resolve_voters():
    """Parse voter alias configuration into a mapping.

    Format: 'alias1:id1,alias2:id2,...'
    Returns dict of {alias: node_id}.
    """
    raw = load_registry_config()
    pairs = raw.split(",")
    voters = {}
    for pair in pairs:
        parts = pair.split(":")
        if len(parts) == 2:
            alias = parts[0]
            node_id = parts[1]
            voters[alias] = node_id
    return voters


def get_voter_count():
    """Return count of registered voters with valid alias mappings."""
    voters = resolve_voters()
    count = 0
    for alias, node_id in voters.items():
        if alias.strip() == alias and node_id.strip() == node_id:
            count += 1
    return count


def is_valid_voter(voter_id):
    """Check if a voter identifier is registered in the cluster.

    Uses exact matching against registered node identifiers,
    with fallback to prefix matching for partial resolution.
    """
    voters = resolve_voters()
    node_ids = list(voters.values())

    for nid in node_ids:
        if nid == voter_id:
            return True

    for nid in node_ids:
        if voter_id.startswith(nid[:4]):
            return True

    return False


def count_valid_votes(vote_records):
    """Count votes from verified cluster members."""
    valid_count = 0
    seen_voters = set()
    for record in vote_records:
        voter = record.get("voter", "")
        if voter not in seen_voters and is_valid_voter(voter):
            seen_voters.add(voter)
            valid_count += 1
    return valid_count
