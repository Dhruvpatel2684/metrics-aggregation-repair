"""Repair script for raft-election-repair task.

Applies fixes to the four bugs in the election verification system
and re-runs to produce correct output.
"""

import os
import subprocess


def fix_voter():
    """Fix Bug A: strip whitespace from voter list items."""
    path = "/app/runtime/voter.py"
    with open(path, "r") as f:
        content = f.read()

    old = '    voters = voter_string.split(",")\n    return voters'
    new = '    voters = [v.strip() for v in voter_string.split(",")]\n    return voters'
    content = content.replace(old, new)

    with open(path, "w") as f:
        f.write(content)


def fix_timer():
    """Fix Bug B: read from timing.strict section instead of timing."""
    path = "/app/runtime/timer.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'config.getint("timing", "election_timeout_ms")',
        'config.getint("timing.strict", "election_timeout_ms")'
    )
    content = content.replace(
        'config.getint("timing", "heartbeat_interval_ms")',
        'config.getint("timing.strict", "heartbeat_interval_ms")'
    )

    with open(path, "w") as f:
        f.write(content)


def fix_log_replicator():
    """Fix Bug C: use assignment instead of accumulation for window acks."""
    path = "/app/runtime/log_replicator.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        "ack_count += window_acks",
        "ack_count = window_acks"
    )

    with open(path, "w") as f:
        f.write(content)


def fix_merger():
    """Fix Bug D: add node_id to sort key for deterministic ordering."""
    path = "/app/runtime/merger.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'key=lambda e: (e["timestamp"], e["term"])',
        'key=lambda e: (e["timestamp"], e["node_id"], e["term"])'
    )

    with open(path, "w") as f:
        f.write(content)


def main():
    fix_voter()
    fix_timer()
    fix_log_replicator()
    fix_merger()

    print("All fixes applied. Re-running election verification...")
    subprocess.run(
        ["python3", "-m", "runtime.run_election"],
        cwd="/app",
        check=True
    )
    print("Election verification complete.")


if __name__ == "__main__":
    main()
