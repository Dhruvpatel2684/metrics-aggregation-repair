"""Repair script for the Raft election reconciliation system.

Applies targeted fixes to five interacting bugs across the runtime modules,
then re-runs the system to produce corrected output.
"""

import os
import subprocess
import sys


def read_file(path):
    with open(path, "r") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w") as f:
        f.write(content)


def fix_epoch_tracker():
    """Fix off-by-one in epoch boundary lookahead comparison."""
    path = "/app/runtime/epoch_tracker.py"
    content = read_file(path)
    content = content.replace(
        'if next_rec["epoch"] >= current_epoch + 1 and records_in_epoch >= threshold:',
        'if next_rec["epoch"] > current_epoch + 1 and records_in_epoch >= threshold:',
    )
    write_file(path, content)


def fix_registry():
    """Fix voter alias parsing whitespace and remove fallback matching."""
    path = "/app/runtime/registry.py"
    content = read_file(path)

    # Fix 1: strip whitespace in alias parsing
    content = content.replace(
        '    pairs = raw.split(",")\n'
        '    voters = {}\n'
        '    for pair in pairs:\n'
        '        parts = pair.split(":")\n'
        '        if len(parts) == 2:\n'
        '            alias = parts[0]\n'
        '            node_id = parts[1]\n'
        '            voters[alias] = node_id',
        '    pairs = raw.split(",")\n'
        '    voters = {}\n'
        '    for pair in pairs:\n'
        '        parts = pair.strip().split(":")\n'
        '        if len(parts) == 2:\n'
        '            alias = parts[0].strip()\n'
        '            node_id = parts[1].strip()\n'
        '            voters[alias] = node_id',
    )

    # Fix 2: remove fallback startswith matching
    content = content.replace(
        '    for nid in node_ids:\n'
        '        if voter_id.startswith(nid[:4]):\n'
        '            return True\n'
        '\n'
        '    return False',
        '    return False',
    )

    write_file(path, content)


def fix_reconciler():
    """Fix accumulator reset between reconciliation phases."""
    path = "/app/runtime/reconciler.py"
    content = read_file(path)

    # Add accumulator reset between phases
    content = content.replace(
        '    for epoch_num, epoch_records in epoch_map.items():\n'
        '        epoch_hbs = [r for r in epoch_records if r["type"] == "hb"]\n'
        '        epoch_hbs.sort(key=lambda r: r["ts"])\n'
        '\n'
        '        if epoch_num not in accumulator:\n'
        '            accumulator[epoch_num] = {}\n'
        '\n'
        '        for i in range(0, len(epoch_hbs), window_size):\n'
        '            window = epoch_hbs[i:i + window_size]\n'
        '            window_idx = i // window_size\n'
        '            ack_sum = sum(r.get("acks", 0) for r in window)\n'
        '            if window_idx in accumulator[epoch_num]:\n'
        '                accumulator[epoch_num][window_idx] += ack_sum\n'
        '            else:\n'
        '                accumulator[epoch_num][window_idx] = ack_sum',
        '    accumulator = {}\n'
        '\n'
        '    for epoch_num, epoch_records in epoch_map.items():\n'
        '        epoch_hbs = [r for r in epoch_records if r["type"] == "hb"]\n'
        '        epoch_hbs.sort(key=lambda r: r["ts"])\n'
        '\n'
        '        if epoch_num not in accumulator:\n'
        '            accumulator[epoch_num] = {}\n'
        '\n'
        '        for i in range(0, len(epoch_hbs), window_size):\n'
        '            window = epoch_hbs[i:i + window_size]\n'
        '            window_idx = i // window_size\n'
        '            ack_sum = sum(r.get("acks", 0) for r in window)\n'
        '            if window_idx in accumulator[epoch_num]:\n'
        '                accumulator[epoch_num][window_idx] += ack_sum\n'
        '            else:\n'
        '                accumulator[epoch_num][window_idx] = ack_sum',
    )

    write_file(path, content)


def fix_merger():
    """Fix sort key ordering for deterministic merge."""
    path = "/app/runtime/merger.py"
    content = read_file(path)
    content = content.replace(
        'unique.sort(key=lambda entry: (entry["ts"], entry["term"], entry["nid"]))',
        'unique.sort(key=lambda entry: (entry["ts"], entry["nid"], entry["term"]))',
    )
    write_file(path, content)


def fix_consensus():
    """Fix voter count to use registry instead of local config parsing."""
    path = "/app/runtime/consensus.py"
    content = read_file(path)

    # Remove the broken local config parsing function and cache
    content = content.replace(
        'def _count_configured_voters():\n'
        '    """Count voters from configuration directly."""\n'
        '    config = configparser.ConfigParser()\n'
        '    config_path = os.path.join(os.path.dirname(__file__), "config", "cluster.ini")\n'
        '    config.read(config_path)\n'
        '    raw = config.get("nodes", "voter_aliases")\n'
        '    pairs = raw.split(",")\n'
        '    count = 0\n'
        '    for pair in pairs:\n'
        '        parts = pair.split(":")\n'
        '        if len(parts) == 2 and parts[0].strip() == parts[0]:\n'
        '            count += 1\n'
        '    return count\n'
        '\n'
        '\n'
        '_cached_voter_count = _count_configured_voters()',
        '',
    )

    # Replace cached access with direct registry call
    content = content.replace(
        '    voter_count = _cached_voter_count\n',
        '    voter_count = registry.get_voter_count()\n',
    )

    write_file(path, content)


def main():
    fix_epoch_tracker()
    fix_registry()
    fix_reconciler()
    fix_merger()
    fix_consensus()

    # Clear any cached bytecode
    cache_dir = "/app/runtime/__pycache__"
    if os.path.exists(cache_dir):
        import shutil
        shutil.rmtree(cache_dir)

    # Re-run the system
    result = subprocess.run(
        [sys.executable, "-m", "runtime.run_election"],
        cwd="/app",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error running election: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout)
    print("All fixes applied and system re-run successfully.")


if __name__ == "__main__":
    main()
