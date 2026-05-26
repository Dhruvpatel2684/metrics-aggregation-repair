# Dependency Graph Topological Resolution Repair

## Overview

You are working with a dependency graph resolver that processes package registries
and produces a topologically sorted manifest of resolved packages. The system
operates as a global system-wide resolution engine that loads package definitions from
JSONL registry files, assigns topological levels based on dependency chain depth,
and produces a deterministic output manifest.

## System Architecture

The resolver is located at `/app/runtime/` and consists of the following components:

- `/app/runtime/run_resolver.py` - Main entry point that orchestrates the full resolution
- `/app/runtime/level_assigner.py` - Assigns topological levels to packages based on chain length boundary from the bounded configuration section
- `/app/runtime/source_registry.py` - Manages source registry filtering with exact alias matching against registered sources
- `/app/runtime/resolver.py` - Performs candidate selection and constraint propagation in two isolated phases with independent visit tracking
- `/app/runtime/topo_sort.py` - Produces the final sorted ordering using (level, name, visit_count) composite key for deterministic output
- `/app/runtime/hasher.py` - Computes integrity hashes for output verification
- `/app/runtime/config/graph.ini` - Configuration for boundaries, registries, and phases
- `/app/runtime/data/` - JSONL registry files containing package definitions

## Data Format

Package registries at `/app/runtime/data/` use JSONL format (one JSON object per line) with abbreviated field names:

- `n` - package name
- `v` - version string (semver)
- `d` - dependency list (array of `{"n": name, "c": constraint}` objects)
- `s` - source registry identifier
- `g` - group/generation number

## Configuration

`/app/runtime/config/graph.ini` defines:

- `[engine]` - Engine identity
- `[sources]` - Registry alias mappings (comma-separated `name:shortcode` pairs)
- `[levels]` and `[levels.bounded]` - Level boundary thresholds for topological assignment
- `[phases]` - Resolution phase definitions

## Output Schema

The resolver produces two JSON files in `/app/runtime/output/`:

### `/app/runtime/output/report.json`

| Field | Type | Description |
|-------|------|-------------|
| `engine_id` | string | Engine instance identifier |
| `levels` | integer | Number of distinct topological levels assigned |
| `packages_resolved` | integer | Total packages successfully resolved |
| `level_distribution` | object | Map of level names to package counts (e.g., `{"L0": 3, "L1": 5, "L2": 7}`) |
| `source_participation` | object | Map of source registry names to package counts from that source |
| `resolution` | object | Resolution metadata including `phase_consistency` boolean and phase statistics |
| `integrity_hash` | string | SHA-256 prefix of canonical report state |

The `level_distribution` field maps level labels (`L0`, `L1`, `L2`, etc.) to the count of packages assigned to each level. With correct boundary assignment, the system produces 3 levels.

The `source_participation` field maps each active source registry name to the number of packages resolved from that source. All configured registries (base, contrib, extended) should appear.

The `resolution` field contains:
- `phase_consistency` (boolean) - True when visit counts from phase 1 match phase 2 (indicating proper per-phase isolation)
- `total_visits` (integer) - Sum of visit counts across all resolved packages
- `phases_run` (integer) - Number of resolution phases executed

### `/app/runtime/output/manifest.json`

| Field | Type | Description |
|-------|------|-------------|
| `metadata` | object | Contains `hash` (SHA-256 prefix of entries array), `total_entries` count |
| `entries` | array | Sorted list of resolved package entries |

Each entry in the `entries` array:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Package name |
| `version` | string | Selected version |
| `level` | integer | Assigned topological level |
| `source` | string | Source registry name |
| `visit_count` | integer | Number of resolution visits to this package |

## Expected Behavior

When functioning correctly, the system should:

1. Load all packages from the three source registries (base, contrib, extended)
2. Assign topological levels using the configured boundary threshold from the bounded strategy section (`[levels.bounded]`)
3. Run resolution in two isolated phases: candidate selection followed by constraint propagation. Each phase maintains independent visit tracking to prevent cross-contamination of metrics between phases.
4. The topological sort orders entries using (level, name, visit_count) composite key to ensure deterministic output regardless of processing order
5. Produce consistent totals: level distribution sum equals packages_resolved equals manifest entry count
6. The level distribution should have exactly 3 levels when the boundary is correctly configured

## Execution

Run the resolver:

```bash
python3 -m runtime.run_resolver
```

This reads registries from `/app/runtime/data/` and writes output to `/app/runtime/output/`.
