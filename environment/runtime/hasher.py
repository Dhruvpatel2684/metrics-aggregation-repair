import hashlib
import json


def hash_report(report_dict):
    """Compute integrity hash for the transform report."""
    to_hash = {k: v for k, v in report_dict.items() if k != "integrity_hash"}
    canonical = json.dumps(to_hash, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def hash_manifest(operations):
    """Compute manifest hash from the operations array."""
    canonical = json.dumps(operations, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
