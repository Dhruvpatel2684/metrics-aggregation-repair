"""Main entry point for the SQL query execution engine.

Orchestrates query parsing, planning, execution, aggregation, sorting,
and result export for all queries defined in the query configuration file.

Usage:
    python3 -m runtime.run_engine
"""

import configparser
import hashlib
import json
import os
import sys
from typing import Any

from runtime.parser import parse_query
from runtime.planner import ExecutionPlanner
from runtime.executor import QueryExecutor
from runtime.aggregator import Aggregator
from runtime.sorter import ResultSorter


def load_config(config_path: str) -> configparser.ConfigParser:
    """Load engine configuration from INI file."""
    config = configparser.ConfigParser()
    config.read(config_path)
    return config


def load_queries(data_dir: str) -> list[dict]:
    """Load query definitions from the queries JSON file."""
    queries_path = os.path.join(data_dir, "queries.json")
    with open(queries_path, "r") as f:
        data = json.load(f)
    return data["queries"]


def compute_integrity_hash(results: list[dict]) -> str:
    """Compute a SHA-256 hash over all query results for integrity verification."""
    hasher = hashlib.sha256()
    for result in results:
        serialized = json.dumps(result["rows"], sort_keys=True, default=str)
        hasher.update(serialized.encode("utf-8"))
    return hasher.hexdigest()


def export_results(
    results: list[dict], output_dir: str, include_stats: bool, include_plan: bool
) -> None:
    """Write query results and metadata to output files."""
    os.makedirs(output_dir, exist_ok=True)

    summary = {
        "query_count": len(results),
        "queries": [],
        "integrity_hash": compute_integrity_hash(results),
    }

    for result in results:
        query_output = {
            "query_id": result["query_id"],
            "description": result["description"],
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": len(result["rows"]),
        }

        if include_stats:
            query_output["statistics"] = result.get("statistics", {})

        if include_plan:
            query_output["execution_plan"] = result.get("plan", {})

        output_path = os.path.join(output_dir, f"{result['query_id']}_result.json")
        with open(output_path, "w") as f:
            json.dump(query_output, f, indent=2, default=str)

        summary["queries"].append({
            "id": result["query_id"],
            "status": "success",
            "row_count": len(result["rows"]),
        })

    summary_path = os.path.join(output_dir, "execution_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)


def run_query(
    query_def: dict, planner: ExecutionPlanner,
    executor: QueryExecutor, aggregator: Aggregator,
    sorter: ResultSorter
) -> dict[str, Any]:
    """Execute a single query through the full processing chain."""
    parsed = parse_query(query_def["sql"])

    plan = planner.build_plan(parsed)

    raw_result = executor.execute(plan, parsed)

    if "partition_groups" in raw_result:
        result = aggregator.aggregate(raw_result)
    else:
        result = raw_result

    sorted_result = sorter.sort(result, parsed["order_by"])

    final_rows = [item["data"] for item in sorted_result["rows"]]

    return {
        "query_id": query_def["id"],
        "description": query_def["description"],
        "columns": sorted_result["columns"],
        "rows": final_rows,
        "plan": plan,
        "statistics": {
            "partitions_processed": len(sorted_result["partitions"]),
            "join_method": plan.get("join_method"),
            "cost_estimate": plan["metadata"]["cost_estimate"],
        },
    }


def main():
    """Main execution flow."""
    config_path = "/app/runtime/config/engine.ini"
    config = load_config(config_path)

    data_dir = config.get("engine", "data_directory")
    output_dir = config.get("engine", "output_directory")
    include_stats = config.getboolean("output", "include_statistics")
    include_plan = config.getboolean("output", "include_plan")

    queries = load_queries(data_dir)

    planner = ExecutionPlanner(config)
    executor = QueryExecutor(config)
    aggregator = Aggregator()
    sorter = ResultSorter()

    results = []
    for query_def in queries:
        try:
            result = run_query(query_def, planner, executor, aggregator, sorter)
            results.append(result)
            print(f"[OK] Query {query_def['id']}: {len(result['rows'])} rows")
        except Exception as e:
            print(f"[ERROR] Query {query_def['id']}: {e}", file=sys.stderr)
            results.append({
                "query_id": query_def["id"],
                "description": query_def["description"],
                "columns": [],
                "rows": [],
                "plan": {},
                "statistics": {"error": str(e)},
            })

    export_results(results, output_dir, include_stats, include_plan)
    print(f"\nExecution complete. {len(results)} queries processed.")
    print(f"Results written to: {output_dir}")


if __name__ == "__main__":
    main()
