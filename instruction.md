# SQL Query Execution Engine — Debugging Task

## Overview

You are given a simplified SQL query execution engine that processes queries against
in-memory table data. The engine parses SQL-like queries, builds execution plans,
processes data in partitions for memory efficiency, and writes structured results
to output files.

The engine currently produces incorrect results for several queries. Your task is
to identify and fix the defects so that all queries produce correct output.

## System Environment

This task uses global system-wide tooling:

- **Python 3.11** runtime environment
- **uv** for dependency management and test execution
- **pytest** for verification (installed via `uv run --with pytest`)

## Project Layout

```
/app/
  runtime/
    __init__.py
    run_engine.py          # Main entry point
    parser.py              # SQL query parser
    planner.py             # Execution plan builder
    executor.py            # Query executor with partition processing
    aggregator.py          # Aggregate function computation
    sorter.py              # Result set sorting
    config/
      engine.ini           # Engine configuration
    data/
      employees.json       # Employee table (20 rows)
      departments.json     # Department table (6 rows)
      queries.json         # Query definitions
    output/                # Results written here
```

## Running the Engine

```bash
cd /app
python3 -m runtime.run_engine
```

This executes all queries from `queries.json` and writes results to the output
directory. Each query produces a `{query_id}_result.json` file and a combined
`execution_summary.json` with an integrity hash.

## Configuration

The engine configuration in `/app/runtime/config/engine.ini` controls:

- **Partition size**: Tables are processed in chunks of `partition_size` rows
- **Join methods**: Available join strategies (hash_join, nested_loop, sort_merge)
- **NULL handling**: How NULL values in GROUP BY columns are treated
- **Output format**: What metadata is included in result files

## Execution Model

1. **Parsing**: SQL strings are decomposed into structured representations
2. **Planning**: The optimizer selects join methods and builds execution stages
3. **Execution**: Queries run partition-by-partition for memory efficiency
4. **Aggregation**: GROUP BY results are merged across partition boundaries
5. **Sorting**: Final results are ordered according to ORDER BY specifications; tied values must maintain original table row position as stable tiebreaker
6. **Export**: Results and statistics are written as JSON files

## Output Schema

Each query result file (`{query_id}_result.json`) contains:

```json
{
  "query_id": "q1",
  "description": "...",
  "columns": ["col1", "col2"],
  "rows": [["val1", "val2"], ...],
  "row_count": 10,
  "statistics": {
    "partitions_processed": 1,
    "join_method": "sort_merge",
    "cost_estimate": 160
  },
  "execution_plan": {
    "stages": [...],
    "partition_size": 10,
    "join_method": "sort_merge",
    "metadata": {...}
  }
}
```

The `execution_summary.json` contains:

```json
{
  "query_count": 4,
  "queries": [
    {"id": "q1", "status": "success", "row_count": 10},
    ...
  ],
  "integrity_hash": "<sha256 hex digest>"
}
```

## Verification

Tests are executed via:

```bash
uv run --with pytest pytest /tests/test_queries.py -v
```

The test suite validates:
- Output file existence and completeness
- Correct row counts and grouping behavior
- Accurate aggregate computations (COUNT, SUM, AVG)
- Proper join method selection
- Deterministic result ordering
- Output integrity hash consistency

## Your Task

Identify defects in the engine source files that cause incorrect query results.
Apply minimal, targeted fixes to the relevant modules. The solution should be
placed in `/solution/repair_engine.py` and invoked via `/solution/solve.sh`.

After applying fixes, the engine must be re-run to regenerate output files
before tests will pass.
