# Dependency Resolution Engine Repair

## Overview

A system-wide package dependency resolution engine processes multi-registry package declarations, constructs a directed dependency graph, performs cycle detection and topological resolution, and outputs a deterministic installation manifest.

The system currently produces structurally valid output but contains defects that cause incorrect resolution results. Your task is to identify and repair the defects so that all validation checks pass.

## System Architecture

The resolution engine operates in the following phases:

1. **Registry Loading** — Reads package declarations from JSONL data files located at `/app/runtime/data/`. Each entry contains abbreviated field names for package metadata.

2. **Source Filtering** — Validates packages against the configured alias-verified source set. Only packages from registries with valid alias entries in `/app/runtime/config/resolver.ini` are admitted.

3. **Cycle Detection** — Traverses the dependency graph using DFS with back-edge identification. Uses an ancestor threshold derived from configuration to determine boundary conditions.

4. **Quality Scoring** — Computes per-package freshness, popularity, and stability metrics across separate registry passes. Each pass processes packages from one source registry independently.

5. **Resolution** — Performs breadth-first traversal with version constraint satisfaction to determine installation depths.

6. **Ordering** — Produces a deterministic installation sequence where packages are ordered by descending resolution depth, then ascending package name, then ascending version string as tiebreakers.

7. **Integrity Hashing** — Computes a SHA-256 digest over the canonical serialization of both the resolution report and the installation manifest.

## File Locations

- Resolver source code: `/app/runtime/`
- Configuration: `/app/runtime/config/resolver.ini`
- Package data: `/app/runtime/data/*.dep`
- Output report: `/app/runtime/output/resolution_report.json`
- Output manifest: `/app/runtime/output/install_manifest.json`
- Test suite: `/tests/test_resolver.py`

## Data Format

Package declarations use JSONL format with abbreviated fields:
- `n` — package name
- `v` — version string
- `d` — dependency array (each element has `n` for name, `c` for version constraint)
- `s` — source registry identifier

## Validation

The test suite validates structural correctness, semantic properties, and system-wide integrity. The integrity hash check requires all resolution components to produce correct results simultaneously — partial fixes will not satisfy this constraint.

## Constraints

- Do not modify test files or data files
- Do not modify the configuration file format
- All repairs must be in the Python source files under `/app/runtime/`
- The system must continue to produce valid JSON output after repairs
