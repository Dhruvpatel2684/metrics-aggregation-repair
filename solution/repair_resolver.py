"""
Repair script for the dependency resolution system.

Applies targeted patches to fix five interacting defects:
A) Off-by-one in cycle detection back-edge boundary
B) Source filter alias parsing (strip) and fallback removal
C) Scorer freshness cache not reset between registry passes
D) Installation order sort key missing package name
E) Resolver using wrong score field for manifest entries
"""

import os
import subprocess
import sys


def patch_file(filepath, replacements):
    """Apply string replacements to a file."""
    with open(filepath, "r") as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"WARNING: Pattern not found in {filepath}: {old[:50]}...")
            continue
        content = content.replace(old, new, 1)
    with open(filepath, "w") as f:
        f.write(content)
    print(f"Patched: {filepath}")


def main():
    base = "/app/runtime"

    # Bug A: Off-by-one in cycle detection boundary
    # >= causes false positive back-edge detection, should be >
    patch_file(
        os.path.join(base, "cycle_detector.py"),
        [
            (
                "if stack_depth >= self._ancestor_count:",
                "if stack_depth > self._ancestor_count:",
            ),
        ],
    )

    # Bug B Part 1: Strip whitespace in alias parsing
    patch_file(
        os.path.join(base, "source_filter.py"),
        [
            (
                "                mapping[source] = alias.strip()",
                "                mapping[source.strip()] = alias.strip()",
            ),
        ],
    )

    # Bug B Part 2: Remove fallback prefix matching
    patch_file(
        os.path.join(base, "source_filter.py"),
        [
            (
                """        for registered, alias in self._alias_map.items():
            if source_name.startswith(alias[:2]):
                return True

        return False""",
                "        return False",
            ),
        ],
    )

    # Bug C: Reset freshness cache between scoring passes
    patch_file(
        os.path.join(base, "scorer.py"),
        [
            (
                '        for pkg in packages:\n            name = pkg["n"]',
                '        self._freshness_cache = {}\n        for pkg in packages:\n            name = pkg["n"]',
            ),
        ],
    )

    # Bug D: Sort key needs package name for deterministic ordering
    patch_file(
        os.path.join(base, "resolver.py"),
        [
            (
                'items.sort(key=lambda x: (-x["depth"], x["version"]))',
                'items.sort(key=lambda x: (-x["depth"], x["name"], x["version"]))',
            ),
        ],
    )

    # Bug E: Wrong score field - should use composite, not freshness
    patch_file(
        os.path.join(base, "resolver.py"),
        [
            (
                'score_entry.get("freshness", 0.0)',
                'score_entry.get("composite", 0.0)',
            ),
        ],
    )

    # Re-run the resolver to generate corrected output
    print("\nRe-running resolver with patches applied...")
    result = subprocess.run(
        [sys.executable, "-m", "runtime.run_resolver"],
        cwd="/app",
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}", file=sys.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
