#!/usr/bin/env python3
"""
Repair script for the connection state recovery pipeline.
Patches identified issues in the runtime modules and regenerates output.
"""

import os
import sys
import re


def patch_sequencer(filepath):
    """Fix event sequencing to use stable deterministic ordering."""
    with open(filepath, "r") as f:
        content = f.read()

    # The sort key must include source to break ties deterministically
    # when events share the same timestamp. Using only (timestamp, seq)
    # causes events from different sources with same seq to be ordered
    # by file load order, which can violate causal dependencies.
    content = content.replace(
        'return sorted(events, key=lambda e: (e["_timestamp"], e.get("seq", 0)))',
        'return sorted(events, key=lambda e: (e["_timestamp"], e["_source"], e.get("seq", 0)))',
    )

    with open(filepath, "w") as f:
        f.write(content)


def patch_event_processor(filepath):
    """Fix pool reservation timeout configuration source."""
    with open(filepath, "r") as f:
        content = f.read()

    # The pool timeout should use the extended timeout value for slow handshakes
    content = content.replace(
        'timeout = self.config.getint("pool", "reservation_timeout_seconds")',
        'timeout = self.config.getint("pool.extended", "reservation_timeout_seconds")',
    )

    with open(filepath, "w") as f:
        f.write(content)


def patch_reconciler(filepath):
    """Fix transition count computation to use final values, not accumulated sums."""
    with open(filepath, "r") as f:
        content = f.read()

    # The reconciler incorrectly sums transition_counts across batch snapshots.
    # A connection appearing in N snapshots gets its count multiplied by N.
    # The correct approach is to use the maximum (final) value from the last snapshot
    # that contains the connection, which represents the actual transition count.
    old_method = '''    def _compute_transition_totals(self, connections, batch_snapshots):
        """
        Compute total transitions for each connection across all batches.
        Accumulates transition counts from batch snapshots for connections
        that appear across multiple processing batches.
        """
        totals = {}
        for snapshot in batch_snapshots:
            for conn_id, data in snapshot.items():
                if conn_id not in totals:
                    totals[conn_id] = 0
                totals[conn_id] += data["transitions_count"]
        return totals'''

    new_method = '''    def _compute_transition_totals(self, connections, batch_snapshots):
        """
        Compute total transitions for each connection across all batches.
        Uses the final transition count from the last snapshot containing
        each connection, representing the actual accumulated transitions.
        """
        totals = {}
        for snapshot in batch_snapshots:
            for conn_id, data in snapshot.items():
                totals[conn_id] = data["transitions_count"]
        return totals'''

    content = content.replace(old_method, new_method)

    with open(filepath, "w") as f:
        f.write(content)


def patch_handlers(filepath):
    """Fix remote event type detection from config parsing."""
    with open(filepath, "r") as f:
        content = f.read()

    # Config values with comma-separated items may contain whitespace.
    # split(",") does not strip individual items, causing " FIN_RECV" != "FIN_RECV"
    old_load = '''    def _load_remote_events(self):
        """Load the set of event types that originate from remote peers."""
        raw = self.config.get("processing", "remote_events", fallback="")
        self._remote_events = set(raw.split(","))'''

    new_load = '''    def _load_remote_events(self):
        """Load the set of event types that originate from remote peers."""
        raw = self.config.get("processing", "remote_events", fallback="")
        self._remote_events = set(item.strip() for item in raw.split(","))'''

    content = content.replace(old_load, new_load)

    with open(filepath, "w") as f:
        f.write(content)


def patch_export(filepath):
    """Fix hash computation to use sorted connection order."""
    with open(filepath, "r") as f:
        content = f.read()

    # Hash must iterate connections in sorted order for deterministic output
    content = content.replace(
        "for conn_id, conn in connections.items():",
        "for conn_id, conn in sorted(connections.items()):",
    )

    with open(filepath, "w") as f:
        f.write(content)


def main():
    base_dir = "/app"
    runtime_dir = os.path.join(base_dir, "runtime")

    patch_sequencer(os.path.join(runtime_dir, "sequencer.py"))
    patch_event_processor(os.path.join(runtime_dir, "event_processor.py"))
    patch_reconciler(os.path.join(runtime_dir, "reconciler.py"))
    patch_handlers(os.path.join(runtime_dir, "handlers.py"))
    patch_export(os.path.join(runtime_dir, "export.py"))

    sys.path.insert(0, base_dir)
    # Re-import after patching (need fresh modules)
    import importlib
    if "runtime" in sys.modules:
        del sys.modules["runtime"]
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]

    from runtime.run_recovery import main as run_main
    run_main()


if __name__ == "__main__":
    main()
