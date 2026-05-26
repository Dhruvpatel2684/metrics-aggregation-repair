#!/usr/bin/env python3
"""Main entry point for the dependency graph resolver."""

import configparser
import json
import os
import glob as glob_mod

from source_registry import SourceRegistry
from level_assigner import LevelAssigner
from resolver import Resolver
from topo_sort import topological_sort
from hasher import compute_manifest_hash


def load_config():
    """Load resolver configuration from graph.ini."""
    config_path = os.path.join(os.path.dirname(__file__), "config", "graph.ini")
    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    return cfg


def load_packages(data_dir):
    """Load all packages from .dep JSONL files in the data directory."""
    packages = []
    dep_files = sorted(glob_mod.glob(os.path.join(data_dir, "*.dep")))
    for dep_file in dep_files:
        with open(dep_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    packages.append(json.loads(line))
    return packages


def run():
    """Execute the full resolution sequence."""
    base_dir = os.path.dirname(__file__)
    data_dir = os.path.join(base_dir, "data")
    output_dir = os.path.join(base_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    config = load_config()
    engine_id = config.get("engine", "id")

    all_packages = load_packages(data_dir)

    registry = SourceRegistry()
    filtered_packages = registry.filter_packages(all_packages)

    assigner = LevelAssigner()
    levels = assigner.assign_levels(filtered_packages)

    resolver = Resolver()
    entries = resolver.resolve(filtered_packages, levels)

    sorted_entries = topological_sort(entries)

    manifest_hash = compute_manifest_hash(sorted_entries)

    level_distribution = {}
    for entry in sorted_entries:
        key = f"L{entry['level']}"
        level_distribution[key] = level_distribution.get(key, 0) + 1

    participating = registry.get_participating_sources(filtered_packages)

    report = {
        "engine_id": engine_id,
        "levels": level_distribution,
        "level_distribution": level_distribution,
        "packages_resolved": len(sorted_entries),
        "source_participation": participating,
        "resolution": {
            "phase_consistency": resolver.phase_consistency,
            "phases_run": 2,
        },
        "integrity_hash": manifest_hash,
    }

    manifest = {
        "entries": sorted_entries,
        "metadata": {
            "total": len(sorted_entries),
            "hash": manifest_hash,
        },
    }

    report_path = os.path.join(output_dir, "report.json")
    manifest_path = os.path.join(output_dir, "manifest.json")

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    run()
