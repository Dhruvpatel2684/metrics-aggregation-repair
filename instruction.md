# Dependency Graph Topological Resolution Repair

## Overview

You are working with a dependency graph resolver that processes package registries
and produces a topologically sorted manifest of resolved packages. The system
operates as a system-wide resolution engine that loads package definitions from
JSONL registry files, assigns topological levels based on dependency chain depth,
and produces a deterministic output manifest.

## System Architecture

The resolver is located at `/app/runtime/` and consists of the following components:

- `/app/runtime/run_resolver.py` - Main entry point that orchestrates the full resolution
- `/app/runtime/level_assigner.py` - Assigns topological levels to packages based on chain length
- `/app/runtime/source_registry.py` - Manages source registry filtering and matching
- `/app/runtime/resolver.py` - Performs candidate selection and constraint propagation
- `/app/runtime/topo_sort.py` - Produces the final sorted ordering of entries
- `/app/runtime/hasher.py` - Computes integrity hashes for output verification
- `/app/runtime/config/graph.ini` - Configuration for boundaries, registries, and phases
- `/app/runtime/data/` - JSONL registry files containing package definitions

## Output

The resolver produces two JSON files in `/app/runtime/output/`:

- `report.json` - Summary report with level distributions, source participation, and resolution metadata
- `manifest.json` - Full sorted manifest of all resolved package entries with integrity hash

## Expected Behavior

When functioning correctly, the system should:

1. Load all packages from the three source registries (base, contrib, extended)
2. Assign topological levels using the configured boundary threshold from the bounded strategy section
3. Run resolution in two isolated phases: candidate selection followed by constraint propagation
4. Resolution phases should maintain per-phase isolation of visit tracking to prevent cross-contamination of metrics between phases
5. The topological sort should order entries for deterministic output using a stable composite key that includes the package name
6. Produce consistent totals across the report level distribution, package count, and manifest entries

## Testing

Tests are located at `/tests/test_resolver.py` and can be run with:

```
uv run --with pytest pytest /tests/test_resolver.py -v
```

The test script at `/tests/test.sh` runs the resolver and then executes the test suite.

## Solution

The repair script at `/solution/repair_resolver.py` can be applied to fix the
resolution issues. Run `/solution/solve.sh` to apply repairs and regenerate output.
