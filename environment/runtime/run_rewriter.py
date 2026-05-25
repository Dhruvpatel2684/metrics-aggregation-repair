"""AST Rewrite Engine - Main Entry Point

Orchestrates the transformation of custom source files through
configurable rewrite rules with scoped visitor analysis.
"""

import configparser
import json
import os
import sys

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_BASE_DIR))

from runtime.rule_loader import load_active_rules
from runtime.scope_resolver import get_max_depth
from runtime.visitor import ASTVisitor
from runtime.rule_chain import apply_rules
from runtime.hasher import hash_report, hash_manifest


def load_config():
    """Load project configuration from transforms.ini."""
    config = configparser.ConfigParser()
    config.read(os.path.join(_BASE_DIR, "config", "transforms.ini"))
    return config


def get_source_files(config):
    """Discover source files in the configured data directory."""
    source_dir = os.path.join(_BASE_DIR, config.get("project", "source_dir"))
    files = []
    for fname in sorted(os.listdir(source_dir)):
        if fname.endswith(".src"):
            files.append(os.path.join(source_dir, fname))
    return files


def run():
    """Execute the AST rewrite engine."""
    config = load_config()
    project_id = config.get("project", "project_id")

    active_rules = load_active_rules()
    max_depth = get_max_depth()

    source_files = get_source_files(config)

    visitor = ASTVisitor(max_depth)
    all_operations = []
    files_processed = {}

    for filepath in source_files:
        filename = os.path.basename(filepath)
        candidates = visitor.process_file(filepath)

        operations = apply_rules(candidates, active_rules, filename)
        all_operations.extend(operations)

        transform_count = len(operations)
        dead_eliminated = len(candidates.get("dead_code", []))
        symbols_resolved = candidates.get("symbols_resolved", 0)

        files_processed[filename] = {
            "transforms": transform_count,
            "symbols_resolved": symbols_resolved,
            "dead_eliminated": dead_eliminated,
        }

    report = {
        "project_id": project_id,
        "total_files": len(source_files),
        "rules_applied": len(all_operations),
        "active_rules": len(active_rules),
        "scope_depth": max_depth,
        "files_processed": files_processed,
    }
    report["integrity_hash"] = hash_report(report)

    manifest = {
        "manifest_hash": hash_manifest(all_operations),
        "operations": all_operations,
    }

    output_dir = os.path.join(_BASE_DIR, config.get("project", "output_dir"))
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "transform_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    with open(os.path.join(output_dir, "rewrite_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    return report, manifest


if __name__ == "__main__":
    run()
