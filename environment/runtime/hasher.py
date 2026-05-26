"""Deterministic hashing for resolution output integrity."""
import hashlib
import json


def hash_report(data_dict):
    """SHA-256 prefix of report (excluding integrity_hash field)."""
    h = {k: v for k, v in data_dict.items() if k != "integrity_hash"}
    canonical = json.dumps(h, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def hash_manifest(items_list):
    """SHA-256 prefix of ordered install manifest."""
    canonical = json.dumps(items_list, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
