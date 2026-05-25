"""Repair script for the SQL query execution engine.

Patches identified issues in the planner, executor, aggregator, and
sorter modules to produce correct query results.
"""

import re


def fix_planner():
    """Fix join method selection to properly strip whitespace from config values."""
    path = "/app/runtime/planner.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        '.split(",")',
        '.split(",")\n        self._allowed_methods = [m.strip() for m in self._allowed_methods]'
    )

    with open(path, "w") as f:
        f.write(content)


def fix_executor():
    """Fix NULL handling to use strict semantics for aggregate queries."""
    path = "/app/runtime/executor.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'self._null_handling = config.get("executor", "null_handling")',
        'self._null_handling = config.get("executor.strict", "null_handling")'
    )

    with open(path, "w") as f:
        f.write(content)


def fix_aggregator():
    """Fix partition snapshot accumulation to use actual row count."""
    path = "/app/runtime/aggregator.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix COUNT: use actual row count instead of summed snapshots
    content = content.replace(
        "effective_count = sum(snapshot_counts)",
        "effective_count = len(rows_in_group)"
    )

    # Fix SUM: use actual values instead of accumulated snapshots
    content = content.replace(
        "if argument in snapshot_sums and snapshot_sums[argument]:\n"
        "                return sum(snapshot_sums[argument])",
        "if values:\n"
        "                return sum(values)"
    )

    with open(path, "w") as f:
        f.write(content)


def fix_sorter():
    """Fix sort tiebreaker to include partition index for deterministic ordering."""
    path = "/app/runtime/sorter.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        '            key_parts.append(item["row_index"])',
        '            key_parts.append((item.get("partition_idx", 0), item["row_index"]))'
    )

    with open(path, "w") as f:
        f.write(content)


if __name__ == "__main__":
    fix_planner()
    fix_executor()
    fix_aggregator()
    fix_sorter()
    print("All patches applied successfully.")

    # Re-run the engine with fixed code
    import sys
    import os
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_engine import main
    main()
