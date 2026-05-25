"""Integrity hashing for compaction report verification.

Produces a deterministic hash of the compaction report to detect
any divergence in the processing state across system components.
"""
import hashlib
import json


def compute_integrity_hash(report_data):
    """Compute SHA-256 integrity hash of the compaction report.
    
    Serializes the report to canonical JSON (sorted keys, no extra
    whitespace) and returns the first 16 hex characters of the
    SHA-256 digest.
    
    Args:
        report_data: dict containing the compaction report fields
    
    Returns:
        str: first 16 hex chars of SHA-256 hash
    """
    # Create canonical representation excluding the hash field itself
    hashable = {k: v for k, v in report_data.items() if k != "integrity_hash"}
    canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]
