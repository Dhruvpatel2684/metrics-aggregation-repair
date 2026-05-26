# Dependency Graph Resolution Engine

## Overview

Global system-wide tooling for package dependency resolution. This engine loads package definitions from registry files, performs topological graph traversal with version constraint satisfaction, detects and removes cycles, scores resolution quality per source registry, and produces deterministic installation manifests.

## Architecture

The resolution engine coordinates several modules at `/app/runtime/`:

- **`/app/runtime/source_filter.py`** — Manages source registry aliases and determines which registries contribute packages to resolution. Each configured source has an alias mapping that controls membership. Packages must pass exact source matching against registered aliases.

- **`/app/runtime/cycle_detector.py`** — DFS-based cycle detection that identifies and removes back-edges in the dependency graph. Uses traversal.bounded parameters for production-safe ancestor thresholds during graph exploration.

- **`/app/runtime/resolver.py`** — Core BFS resolution that satisfies version constraints and computes deterministic installation order. The installation ordering uses (depth descending, package name, version) composite key to ensure reproducible plans across runs.

- **`/app/runtime/scorer.py`** — Computes freshness and quality metrics for the resolved set. Each source registry is scored independently with isolated accumulation state to prevent cross-source contamination between scoring passes.

- **`/app/runtime/hasher.py`** — SHA-256 based integrity hashing for canonical output verification.

## Data Format

Package registries at `/app/runtime/data/` use JSONL format (one JSON object per line) with abbreviated field names:

- `n` — package name
- `v` — version string (semver)
- `d` — dependency list (array of `{n, c}` objects where `c` is constraint like `>=2.1.0`)
- `s` — source registry name
- `p` — priority (1 = newest, higher = older)

## Configuration

`/app/runtime/config/resolver.ini` defines:

- `[engine]` — Engine identity and strategy
- `[sources]` — Source registry alias mappings (`name:shortcode` comma-separated)
- `[traversal]` and `[traversal.bounded]` — Cycle detection thresholds
- `[scoring]` — Quality scoring weights
- `[output]` — Output format settings

## Output Schema

### `/app/runtime/output/resolution_report.json`

| Field | Type | Description |
|-------|------|-------------|
| `engine_id` | string | Engine instance identifier |
| `strategy` | string | Resolution strategy name |
| `ancestor_threshold` | integer | Configured cycle detection depth |
| `active_sources` | integer | Count of registered source registries |
| `packages_available` | integer | Total package versions in filtered set |
| `packages_resolved` | integer | Packages successfully resolved |
| `install_order_length` | integer | Entries in installation plan |
| `scoring` | object | Resolution quality metrics |
| `integrity_hash` | string | SHA-256 prefix of canonical report state |

### `/app/runtime/output/install_manifest.json`

| Field | Type | Description |
|-------|------|-------------|
| `manifest_hash` | string | SHA-256 prefix of install order |
| `install_order` | array | Ordered installation entries |

Each entry in `install_order`:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Package name |
| `version` | string | Selected version |
| `source` | string | Source registry |
| `depth` | integer | Resolution depth from root |
| `dep_count` | integer | Direct dependency count |

## Execution

```bash
python3 -m runtime.run_resolver
```

Reads registries from `/app/runtime/data/` and writes output to `/app/runtime/output/`.
