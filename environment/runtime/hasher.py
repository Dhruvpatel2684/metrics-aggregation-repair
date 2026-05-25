"""Deterministic hashing for output integrity verification."""

import hashlib
import json


def hash_manifest(entries):
    """Compute truncated SHA-256 hash of canonical manifest entries."""
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def hash_state(state_dict):
    """Compute truncated SHA-256 hash of reconciliation state.

    Excludes the integrity_hash field itself from computation.
    """
    to_hash = {k: v for k, v in state_dict.items() if k != "integrity_hash"}
    canonical = json.dumps(to_hash, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
