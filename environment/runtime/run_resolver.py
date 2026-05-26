"""Dependency graph resolver - main orchestrator."""
import json
import os

from runtime.config import get_config
from runtime.source_filter import get_active_sources, get_source_count, filter_packages
from runtime.cycle_detector import get_ancestor_threshold
from runtime.resolver import resolve
from runtime.scorer import ResolutionScorer
from runtime.hasher import hash_report, hash_manifest


def load_packages(data_dir):
    """Load all .dep registry files (JSONL format)."""
    packages = {}
    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith(".dep"):
            continue
        with open(os.path.join(data_dir, fname)) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                entry = json.loads(line)
                name = entry["n"]
                if name not in packages:
                    packages[name] = []
                packages[name].append(entry)
    # Sort each package's versions by priority (p field, lower = newer)
    for name in packages:
        packages[name].sort(key=lambda e: e.get("p", 99))
    return packages


def main():
    config = get_config()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    output_dir = os.path.join(base_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    all_packages = load_packages(data_dir)
    active_sources = get_active_sources()
    filtered = filter_packages(all_packages)

    root_reqs = [("platform", ">=5.9.0")]
    result = resolve(root_reqs, filtered)

    resolved = result["resolved"]
    depth_map = result["depth_map"]
    install_order = result["install_order"]

    scorer = ResolutionScorer(filtered)
    # Validation pass to check for source connectivity
    scorer.score(resolved, depth_map, active_sources)
    # Final scoring pass
    scoring = scorer.score(resolved, depth_map, active_sources)

    report = {
        "engine_id": config.get("engine", "engine_id"),
        "strategy": config.get("engine", "strategy"),
        "ancestor_threshold": get_ancestor_threshold(),
        "active_sources": get_source_count(),
        "packages_available": sum(len(v) for v in filtered.values()),
        "packages_resolved": len(resolved),
        "install_order_length": len(install_order),
        "scoring": scoring,
    }
    report["integrity_hash"] = hash_report(report)

    manifest = {
        "manifest_hash": hash_manifest(install_order),
        "install_order": install_order,
    }

    with open(os.path.join(output_dir, "resolution_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    with open(os.path.join(output_dir, "install_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Resolution complete: {len(resolved)} packages")
    print(f"Install order: {len(install_order)} packages")


if __name__ == "__main__":
    main()
