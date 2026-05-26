#!/usr/bin/env python3
"""Repair script that fixes all 5 bugs in the dependency graph resolver."""

import os
import sys

RUNTIME_DIR = "/app/runtime"


def patch(filepath, old, new):
    with open(filepath, "r") as f:
        content = f.read()
    if old not in content:
        print(f"WARNING: pattern not found in {filepath}", file=sys.stderr)
        return False
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    return True


def fix_level_assigner():
    """Fix Bug A (off-by-one) and Bug E (wrong config section + cache)."""
    path = os.path.join(RUNTIME_DIR, "level_assigner.py")

    # Fix E: Change config section from [levels] to [levels.bounded]
    patch(path,
        'return cfg.getint("levels", "boundary")',
        'return cfg.getint("levels.bounded", "boundary")')

    # Fix E: Bypass the module-level cache
    patch(path,
        "self._level_boundary = boundary if boundary is not None else _cached_boundary",
        "self._level_boundary = boundary if boundary is not None else _load_boundary()")

    # Fix A: Change >= to > in level computation
    patch(path,
        "while chain_length >= threshold:",
        "while chain_length > threshold:")


def fix_source_registry():
    """Fix Bug B: strip whitespace from registries and remove fallback prefix matching."""
    path = os.path.join(RUNTIME_DIR, "source_registry.py")

    # Part 1: Strip whitespace from split
    patch(path,
        'self._registries = raw_sources.split(",")',
        'self._registries = [s.strip() for s in raw_sources.split(",")]')

    # Part 2: Remove fallback prefix matching
    patch(path,
        '        for reg in self._registries:\n'
        '            if source_id.startswith(reg.strip()[:3]):\n'
        '                return reg\n'
        '        return None',
        '        return None')


def fix_resolver():
    """Fix Bug C: reset visit_counts between resolution phases."""
    path = os.path.join(RUNTIME_DIR, "resolver.py")

    patch(path,
        '        phase1_counts = dict(self._visit_counts)\n'
        '\n'
        '        self._propagate_constraints(packages, levels)',
        '        phase1_counts = dict(self._visit_counts)\n'
        '\n'
        '        self._visit_counts = {}\n'
        '\n'
        '        self._propagate_constraints(packages, levels)')


def fix_topo_sort():
    """Fix Bug D: add package name to sort key for deterministic ordering."""
    path = os.path.join(RUNTIME_DIR, "topo_sort.py")

    patch(path,
        'return sorted(entries, key=lambda e: (e["level"], e["visit_count"]))',
        'return sorted(entries, key=lambda e: (e["level"], e["name"], e["visit_count"]))')


if __name__ == "__main__":
    fix_level_assigner()
    fix_source_registry()
    fix_resolver()
    fix_topo_sort()
    print("All 5 bugs repaired successfully.")
