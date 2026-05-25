#!/usr/bin/env python3
"""
Repair script for the spatial indexing system.
Patches identified issues in the runtime modules and regenerates output.
"""

import os
import sys


def patch_geometry(filepath):
    """Fix geometry type filtering from config parsing."""
    with open(filepath, "r") as f:
        content = f.read()

    # Config values with comma-separated items may contain whitespace.
    # split(",") does not strip individual items, causing " LineString" != "LineString"
    old_load = '''    def _load_supported_types(self):
        """Load the set of geometry types that this processor supports."""
        raw = self.config.get("geometry", "supported_types", fallback="")
        self._supported_types = set(raw.split(","))'''

    new_load = '''    def _load_supported_types(self):
        """Load the set of geometry types that this processor supports."""
        raw = self.config.get("geometry", "supported_types", fallback="")
        self._supported_types = set(item.strip() for item in raw.split(","))'''

    content = content.replace(old_load, new_load)

    with open(filepath, "w") as f:
        f.write(content)


def patch_query_engine(filepath):
    """Fix spatial tolerance configuration source."""
    with open(filepath, "r") as f:
        content = f.read()

    # The tolerance should use the precision-grade value from query.precision section
    content = content.replace(
        'self.tolerance = self.config.getfloat("query", "spatial_tolerance_degrees")',
        'self.tolerance = self.config.getfloat("query.precision", "spatial_tolerance_degrees")',
    )

    with open(filepath, "w") as f:
        f.write(content)


def patch_reconciler(filepath):
    """Fix area computation to use final values, not accumulated sums."""
    with open(filepath, "r") as f:
        content = f.read()

    # The reconciler incorrectly sums area_sqm across window snapshots.
    # A feature appearing in multiple windows (same ID in different sectors)
    # gets its area accumulated. The correct approach is to use the value
    # from the last snapshot (last-write-wins semantics for deduplication).
    old_method = '''    def _reconcile_snapshots(self, window_snapshots):
        """
        Reconcile feature data across all window snapshots.
        Computes area totals for each unique feature by accumulating
        area contributions from each window snapshot that contains it.
        """
        area_totals = {}
        final_features = {}

        for snapshot in window_snapshots:
            for fid, data in snapshot.items():
                if fid not in area_totals:
                    area_totals[fid] = 0.0
                area_totals[fid] += data["area_sqm"]
                final_features[fid] = data

        # Apply reconciled area totals
        for fid, feature in final_features.items():
            feature["area_sqm"] = area_totals[fid]

        return list(final_features.values())'''

    new_method = '''    def _reconcile_snapshots(self, window_snapshots):
        """
        Reconcile feature data across all window snapshots.
        Uses the final area value from the last snapshot containing
        each feature, representing the authoritative area measurement.
        """
        area_totals = {}
        final_features = {}

        for snapshot in window_snapshots:
            for fid, data in snapshot.items():
                area_totals[fid] = data["area_sqm"]
                final_features[fid] = data

        # Apply reconciled area totals
        for fid, feature in final_features.items():
            feature["area_sqm"] = area_totals[fid]

        return list(final_features.values())'''

    content = content.replace(old_method, new_method)

    with open(filepath, "w") as f:
        f.write(content)


def patch_ingest(filepath):
    """Fix sector sort ordering to include source priority for deterministic dedup."""
    with open(filepath, "r") as f:
        content = f.read()

    # The sort key must include source priority to ensure lower-priority sources
    # are processed before higher-priority ones within the same sector/seq group.
    # This guarantees that last-write-wins deduplication correctly selects
    # the most authoritative source (lowest priority number = most authoritative).
    # Without this, load order determines winner, which may not match priority.
    content = content.replace(
        'return sorted(features, key=lambda f: (f["_sector"], f.get("_seq", 0)))',
        'return sorted(features, key=lambda f: (f["_sector"], f.get("_seq", 0), -f["_source_priority"]))',
    )

    with open(filepath, "w") as f:
        f.write(content)


def main():
    base_dir = "/app"
    runtime_dir = os.path.join(base_dir, "runtime")

    patch_geometry(os.path.join(runtime_dir, "geometry.py"))
    patch_query_engine(os.path.join(runtime_dir, "query_engine.py"))
    patch_reconciler(os.path.join(runtime_dir, "reconciler.py"))
    patch_ingest(os.path.join(runtime_dir, "ingest.py"))

    sys.path.insert(0, base_dir)
    # Re-import after patching (need fresh modules)
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]

    from runtime.run_indexer import main as run_main
    run_main()


if __name__ == "__main__":
    main()
