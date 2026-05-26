"""
Integrity hash computation for resolution output.

Produces a deterministic SHA-256 digest over the resolution
and manifest data to verify system-wide correctness.
"""

import hashlib
import json


class IntegrityHasher:
    """Computes integrity hash over resolution output data."""

    def __init__(self):
        self._hasher = hashlib.sha256()

    def hash_report(self, report_data):
        """
        Compute hash over the resolution report structure.
        Serializes with sorted keys for determinism.
        """
        canonical = json.dumps(report_data, sort_keys=True, separators=(",", ":"))
        self._hasher.update(canonical.encode("utf-8"))

    def hash_manifest(self, manifest_data):
        """
        Compute hash over the installation manifest.
        Order-sensitive to capture install sequence.
        """
        canonical = json.dumps(manifest_data, sort_keys=False, separators=(",", ":"))
        self._hasher.update(canonical.encode("utf-8"))

    def finalize(self):
        """Return the hex digest of all hashed data."""
        return self._hasher.hexdigest()

    @staticmethod
    def quick_hash(data):
        """One-shot hash of arbitrary JSON-serializable data."""
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
