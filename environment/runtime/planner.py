"""Query execution planner.

Builds execution plans by selecting optimal join methods, determining
scan strategies, and organizing the execution pipeline based on the
parsed query structure and engine configuration.
"""

import configparser
from typing import Any


class ExecutionPlanner:
    """Constructs execution plans from parsed queries and configuration."""

    def __init__(self, config: configparser.ConfigParser):
        self._config = config
        self._partition_size = config.getint("engine", "partition_size")
        self._preferred_method = config.get("optimizer", "preferred_join_method")
        self._allowed_methods = config.get(
            "optimizer", "allowed_join_methods"
        ).split(",")
        self._cost_threshold = config.getint("optimizer", "cost_threshold")
        self._pushdown = config.getboolean("optimizer", "enable_predicate_pushdown")

    def build_plan(self, parsed_query: dict[str, Any]) -> dict[str, Any]:
        """Build an execution plan for the given parsed query.

        The plan includes scan nodes, filter nodes, join strategy,
        aggregation stage, and final sort specification.
        """
        plan = {
            "stages": [],
            "partition_size": self._partition_size,
            "join_method": None,
            "metadata": {
                "cost_estimate": 0,
                "predicate_pushdown": self._pushdown,
            },
        }

        for table in parsed_query["tables"]:
            scan_stage = {
                "type": "scan",
                "table": table["name"],
                "alias": table["alias"],
                "partition_size": self._partition_size,
            }
            plan["stages"].append(scan_stage)

        if parsed_query["filters"] and self._pushdown:
            filter_stage = {
                "type": "filter",
                "predicates": parsed_query["filters"],
                "pushed_down": True,
            }
            plan["stages"].append(filter_stage)
            plan["metadata"]["cost_estimate"] += len(parsed_query["filters"]) * 10

        if parsed_query["joins"]:
            join_method = self._select_join_method(parsed_query)
            join_stage = {
                "type": "join",
                "method": join_method,
                "conditions": parsed_query["joins"],
            }
            plan["stages"].append(join_stage)
            plan["join_method"] = join_method
            plan["metadata"]["cost_estimate"] += self._estimate_join_cost(join_method)

        if parsed_query["group_by"]:
            agg_stage = {
                "type": "aggregate",
                "group_by": parsed_query["group_by"],
                "functions": parsed_query["aggregates"],
            }
            plan["stages"].append(agg_stage)
            plan["metadata"]["cost_estimate"] += 50

        if parsed_query["order_by"]:
            sort_stage = {
                "type": "sort",
                "keys": parsed_query["order_by"],
            }
            plan["stages"].append(sort_stage)
            plan["metadata"]["cost_estimate"] += 30

        return plan

    def _select_join_method(self, parsed_query: dict[str, Any]) -> str:
        """Select the best join method based on configuration and query hints.

        Checks if the preferred method is available in the allowed methods
        list. Falls back to the first allowed method if not found.
        """
        hint = parsed_query.get("method_hint")
        candidate = hint if hint else self._preferred_method

        if candidate in self._allowed_methods:
            return candidate

        return self._allowed_methods[0]

    def _estimate_join_cost(self, method: str) -> int:
        """Estimate relative cost of a join method."""
        costs = {
            "hash_join": 100,
            "nested_loop": 500,
            "sort_merge": 150,
        }
        return costs.get(method, 200)
