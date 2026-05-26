"""
Dependency Resolution Orchestrator

Loads package registries, applies source filtering, detects cycles,
scores packages, resolves dependencies, and writes output manifests.
"""

import json
import os
import configparser

from runtime.source_filter import SourceFilter
from runtime.cycle_detector import CycleDetector
from runtime.scorer import PackageScorer
from runtime.resolver import DependencyResolver
from runtime.hasher import IntegrityHasher


def load_registry(filepath):
    """Load a JSONL registry file into a list of package dicts."""
    packages = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                packages.append(json.loads(line))
    return packages


def build_adjacency(packages):
    """
    Build directed adjacency from package dependency declarations.
    Keys are 'name@version', values are lists of dependency keys.
    """
    pkg_lookup = {}
    for pkg in packages:
        key = f"{pkg['n']}@{pkg['v']}"
        pkg_lookup[key] = pkg

    adjacency = {f"{pkg['n']}@{pkg['v']}": [] for pkg in packages}

    for pkg in packages:
        src_key = f"{pkg['n']}@{pkg['v']}"
        for dep in pkg.get("d", []):
            dep_name = dep["n"]
            candidates = [k for k in adjacency if k.startswith(f"{dep_name}@")]
            for candidate in candidates:
                cand_pkg = pkg_lookup.get(candidate)
                if cand_pkg:
                    constraint = dep.get("c", "")
                    from runtime.resolver import VersionConstraint
                    if VersionConstraint.satisfies(cand_pkg["v"], constraint):
                        adjacency[src_key].append(candidate)
                        break

    return adjacency


def main():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(os.path.dirname(__file__), "config", "resolver.ini"))

    data_dir = cfg.get("registry", "data_directory",
                       fallback="/app/runtime/data")
    output_dir = cfg.get("registry", "output_directory",
                        fallback="/app/runtime/output")

    if not os.path.isdir(data_dir):
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    if not os.path.isdir(output_dir):
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

    os.makedirs(output_dir, exist_ok=True)

    source_filter = SourceFilter()

    all_packages = []
    registry_files = sorted([
        f for f in os.listdir(data_dir) if f.endswith(".dep")
    ])

    for reg_file in registry_files:
        filepath = os.path.join(data_dir, reg_file)
        packages = load_registry(filepath)
        all_packages.extend(packages)

    filtered = source_filter.filter_packages(all_packages)

    adjacency = build_adjacency(filtered)

    root_nodes = []
    all_targets = set()
    for deps in adjacency.values():
        all_targets.update(deps)
    root_nodes = [k for k in adjacency if k not in all_targets]

    detector = CycleDetector(adjacency, root_nodes)
    clean_adj, removed_edges = detector.detect_and_remove()

    scorer = PackageScorer()
    registries_seen = {}
    for pkg in filtered:
        reg = pkg.get("s", "unknown")
        if reg not in registries_seen:
            registries_seen[reg] = []
        registries_seen[reg].append(pkg)

    for registry_name, reg_packages in registries_seen.items():
        scorer.score_registry_pass(registry_name, reg_packages)

    scores = scorer.get_all_scores()

    resolver = DependencyResolver(filtered, clean_adj, scores)
    install_order = resolver.resolve()

    hasher = IntegrityHasher()

    report = {
        "metadata": {
            "total_packages": len(filtered),
            "source_count": source_filter.get_source_count(),
            "registries_processed": list(registries_seen.keys()),
            "removed_cycles": [(a, b) for a, b in removed_edges],
            "max_depth": resolver.get_resolution_depth(),
            "scoring_passes": scorer.get_pass_count()
        },
        "scores": scores
    }

    manifest = {
        "install_order": [
            {
                "name": item["name"],
                "version": item["version"],
                "source": item["source"],
                "depth": item["depth"],
                "score": item["score"]
            }
            for item in install_order
        ],
        "total_install_count": len(install_order)
    }

    hasher.hash_report(report)
    hasher.hash_manifest(manifest)
    integrity = hasher.finalize()

    report["metadata"]["integrity_hash"] = integrity
    manifest["integrity_hash"] = integrity

    report_path = os.path.join(output_dir, "resolution_report.json")
    manifest_path = os.path.join(output_dir, "install_manifest.json")

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Resolution complete: {len(install_order)} packages resolved")
    print(f"Report written to {report_path}")
    print(f"Manifest written to {manifest_path}")
    print(f"Integrity hash: {integrity}")


if __name__ == "__main__":
    main()
