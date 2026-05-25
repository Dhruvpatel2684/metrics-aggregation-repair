"""Repair script for the time-series compaction engine.

Patches five interacting defects in the compaction processing chain
and re-runs the engine to produce correct output.
"""
import subprocess
import sys


def fix_collector_filter():
    """Fix whitespace handling in active collector list parsing."""
    path = "/app/runtime/collector_filter.py"
    with open(path, "r") as f:
        content = f.read()
    
    content = content.replace(
        "collectors = collector_str.split(\",\")",
        "collectors = [c.strip() for c in collector_str.split(\",\")]"
    )
    
    with open(path, "w") as f:
        f.write(content)


def fix_aligner():
    """Fix windowing section reference and cached offset invalidation."""
    path = "/app/runtime/aligner.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Fix config section reference
    content = content.replace(
        'return config.getint("windowing", "alignment_offset_ms")',
        'return config.getint("windowing.precise", "alignment_offset_ms")'
    )
    
    # Fix cached offset - reload after config section fix
    content = content.replace(
        "# Pre-computed alignment offset for performance during bulk processing\n"
        "_cached_offset = _load_alignment()",
        "# Pre-computed alignment offset for performance during bulk processing\n"
        "_cached_offset = _load_alignment()\n"
    )
    
    # Replace align_timestamp to use fresh value
    content = content.replace(
        "def align_timestamp(ts, window_ms):\n"
        "    \"\"\"Align a timestamp to its window boundary.\n"
        "    \n"
        "    Computes the start of the window that contains the given timestamp,\n"
        "    accounting for the configured alignment offset.\n"
        "    \n"
        "    Args:\n"
        "        ts: epoch timestamp in milliseconds\n"
        "        window_ms: window size in milliseconds\n"
        "    \n"
        "    Returns:\n"
        "        window start timestamp in milliseconds\n"
        "    \"\"\"\n"
        "    offset = _cached_offset\n"
        "    aligned = ((ts - offset) // window_ms) * window_ms + offset\n"
        "    return aligned",
        "def align_timestamp(ts, window_ms):\n"
        "    \"\"\"Align a timestamp to its window boundary.\n"
        "    \n"
        "    Computes the start of the window that contains the given timestamp,\n"
        "    accounting for the configured alignment offset.\n"
        "    \n"
        "    Args:\n"
        "        ts: epoch timestamp in milliseconds\n"
        "        window_ms: window size in milliseconds\n"
        "    \n"
        "    Returns:\n"
        "        window start timestamp in milliseconds\n"
        "    \"\"\"\n"
        "    offset = _load_alignment()\n"
        "    aligned = ((ts - offset) // window_ms) * window_ms + offset\n"
        "    return aligned"
    )
    
    # Also fix get_alignment_offset to return fresh value
    content = content.replace(
        "def get_alignment_offset():\n"
        "    \"\"\"Return the current alignment offset in milliseconds.\"\"\"\n"
        "    return _cached_offset",
        "def get_alignment_offset():\n"
        "    \"\"\"Return the current alignment offset in milliseconds.\"\"\"\n"
        "    return _load_alignment()"
    )
    
    with open(path, "w") as f:
        f.write(content)


def fix_rollup():
    """Fix tier accumulator reset between retention tiers."""
    path = "/app/runtime/rollup.py"
    with open(path, "r") as f:
        content = f.read()
    
    content = content.replace(
        "        # Group by window\n"
        "        groups = {}",
        "        # Reset accumulators for tier independence\n"
        "        self.running_sum = {}\n"
        "        self.running_count = {}\n"
        "        # Group by window\n"
        "        groups = {}"
    )
    
    with open(path, "w") as f:
        f.write(content)


def fix_sorter():
    """Fix sort key for deterministic ordering."""
    path = "/app/runtime/sorter.py"
    with open(path, "r") as f:
        content = f.read()
    
    content = content.replace(
        'return sorted(points, key=lambda p: (p["ts"], p["value"]))',
        'return sorted(points, key=lambda p: (p["ts"], p["collector"], p["metric"]))'
    )
    
    with open(path, "w") as f:
        f.write(content)


def main():
    """Apply all fixes and re-run the compaction engine."""
    fix_collector_filter()
    fix_aligner()
    fix_rollup()
    fix_sorter()
    
    # Re-run the compactor with fixes applied
    subprocess.run(
        [sys.executable, "-m", "runtime.run_compactor"],
        cwd="/app",
        check=True
    )
    print("Repair complete: all defects patched and compactor re-executed")


if __name__ == "__main__":
    main()
