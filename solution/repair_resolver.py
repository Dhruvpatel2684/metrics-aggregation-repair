"""Repair script for dep-graph-repair task."""
import os
import shutil
import subprocess
import sys

RUNTIME = "/app/runtime"


def patch(path, old, new):
    with open(path) as f:
        content = f.read()
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)


def fix_source_filter():
    """Fix A: strip aliases + remove fallback matching."""
    path = os.path.join(RUNTIME, "source_filter.py")
    # Strip aliases
    patch(path,
        '    pairs = raw.split(",")\n'
        '    aliases = {}\n'
        '    for pair in pairs:\n'
        '        parts = pair.split(":")\n'
        '        if len(parts) == 2:\n'
        '            alias = parts[0]\n'
        '            short = parts[1]\n'
        '            aliases[alias] = short',
        '    pairs = raw.split(",")\n'
        '    aliases = {}\n'
        '    for pair in pairs:\n'
        '        parts = pair.strip().split(":")\n'
        '        if len(parts) == 2:\n'
        '            alias = parts[0].strip()\n'
        '            short = parts[1].strip()\n'
        '            aliases[alias] = short')
    # Remove fallback
    patch(path,
        '    for registered in source_set:\n'
        '        if source_name.startswith(registered.strip()[:3]):\n'
        '            return True\n'
        '\n'
        '    return False',
        '    return False')


def fix_cycle_detector():
    """Fix B+E: correct config section and bypass cache."""
    path = os.path.join(RUNTIME, "cycle_detector.py")
    # Fix config section
    patch(path,
        'return config.getint("traversal", "max_ancestors")',
        'return config.getint("traversal.bounded", "max_ancestors")')
    # Fix cache bypass
    patch(path,
        '    return _cached_threshold',
        '    return _compute_threshold()')


def fix_scorer():
    """Fix C: reset accumulator between scoring passes."""
    path = os.path.join(RUNTIME, "scorer.py")
    patch(path,
        '        source_scores = {}\n'
        '        total_freshness = 0.0\n'
        '        total_count = 0',
        '        self._score_accumulator = {}\n'
        '        source_scores = {}\n'
        '        total_freshness = 0.0\n'
        '        total_count = 0')


def fix_resolver():
    """Fix D: correct sort key for deterministic ordering."""
    path = os.path.join(RUNTIME, "resolver.py")
    patch(path,
        'items.sort(key=lambda x: (-x["depth"], x["version"]))',
        'items.sort(key=lambda x: (-x["depth"], x["name"], x["version"]))')


def main():
    fix_source_filter()
    fix_cycle_detector()
    fix_scorer()
    fix_resolver()

    # Clear bytecode
    for root, dirs, _ in os.walk(RUNTIME):
        for d in dirs:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d))

    result = subprocess.run(
        [sys.executable, "-m", "runtime.run_resolver"],
        cwd="/app", capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout)
    print("All fixes applied successfully.")


if __name__ == "__main__":
    main()
