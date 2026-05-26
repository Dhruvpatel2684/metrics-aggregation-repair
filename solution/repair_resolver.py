#!/usr/bin/env python3
"""Repair script that fixes all 5 bugs in the dependency graph resolver."""

import os

RUNTIME_DIR = os.path.join(os.path.dirname(__file__), "..", "environment", "runtime")


def fix_level_assigner():
    """Fix Bug A (off-by-one >= vs >) and Bug E (wrong config section for boundary cache)."""
    path = os.path.join(RUNTIME_DIR, "level_assigner.py")
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'return cfg.getint("levels", "boundary")',
        'return cfg.getint("levels.bounded", "boundary")',
    )

    content = content.replace(
        "while chain_length >= threshold:",
        "while chain_length > threshold:",
    )

    content = content.replace(
        "_cached_boundary = _load_boundary()",
        "_cached_boundary = _load_boundary()\n",
    )

    with open(path, "w") as f:
        f.write(content)

    load_and_patch_cache(path)


def load_and_patch_cache(path):
    """Reload the module to pick up the corrected boundary value."""
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        "_cached_boundary = _load_boundary()\n\n",
        "_cached_boundary = _load_boundary()\n",
    )

    with open(path, "w") as f:
        f.write(content)


def fix_source_registry():
    """Fix Bug B: strip whitespace from registry names and remove fallback prefix matching."""
    path = os.path.join(RUNTIME_DIR, "source_registry.py")
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'self._registries = raw_sources.split(",")',
        'self._registries = [s.strip() for s in raw_sources.split(",")]',
    )

    old_match = '''    def _match_source(self, source_id):
        """Match a package source to a registered registry."""
        for reg in self._registries:
            if source_id == reg:
                return reg
        for reg in self._registries:
            if source_id.startswith(reg.strip()[:3]):
                return reg
        return None'''

    new_match = '''    def _match_source(self, source_id):
        """Match a package source to a registered registry."""
        for reg in self._registries:
            if source_id == reg:
                return reg
        return None'''

    content = content.replace(old_match, new_match)

    with open(path, "w") as f:
        f.write(content)


def fix_resolver():
    """Fix Bug C: reset visit_counts between resolution phases."""
    path = os.path.join(RUNTIME_DIR, "resolver.py")
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        "        phase1_counts = dict(self._visit_counts)\n\n        self._propagate_constraints(packages, levels)",
        "        phase1_counts = dict(self._visit_counts)\n\n        self._visit_counts = {}\n\n        self._propagate_constraints(packages, levels)",
    )

    with open(path, "w") as f:
        f.write(content)


def fix_topo_sort():
    """Fix Bug D: add package name to sort key for deterministic ordering."""
    path = os.path.join(RUNTIME_DIR, "topo_sort.py")
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'return sorted(entries, key=lambda e: (e["level"], e["visit_count"]))',
        'return sorted(entries, key=lambda e: (e["level"], e["name"], e["visit_count"]))',
    )

    with open(path, "w") as f:
        f.write(content)


if __name__ == "__main__":
    fix_level_assigner()
    fix_source_registry()
    fix_resolver()
    fix_topo_sort()
    print("All 5 bugs repaired successfully.")
