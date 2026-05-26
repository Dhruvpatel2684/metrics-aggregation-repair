import hashlib
import json


def compute_manifest_hash(entries):
    """Compute SHA-256 hash of the sorted manifest entries."""
    serialized = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
