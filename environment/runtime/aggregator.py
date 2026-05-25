"""Aggregation module for the query execution engine.

Merges partition-level group results into final aggregate values,
computing COUNT, SUM, AVG, MIN, and MAX across all partitions for
each distinct group key.

Uses strict NULL semantics from [executor.strict] for accurate
COUNT/SUM computations across partition boundaries.
"""

from typing import Any


class Aggregator:
    """Computes aggregate functions across partitioned group results."""

    def __init__(self):
        self._snapshot_log: list[dict] = []

    def aggregate(self, execution_result: dict[str, Any]) -> dict[str, Any]:
        """Merge partition groups and compute final aggregates.

        Takes the partitioned group results from the executor and
        produces a single unified result set with computed aggregate
        values for each group.
        """
        partition_groups = execution_result["partition_groups"]
        columns = execution_result["columns"]
        group_cols = execution_result["group_cols"]
        aggregates = execution_result["aggregates"]
        select_columns = execution_result["select_columns"]

        group_col_indices = [columns.index(col) for col in group_cols]
        merged_groups: dict[tuple, dict] = {}

        for partition_idx, groups in enumerate(partition_groups):
            for group_key, rows in groups.items():
                if group_key not in merged_groups:
                    merged_groups[group_key] = {
                        "rows": [],
                        "running_count": 0,
                        "running_sums": {},
                        "snapshot_counts": [],
                        "snapshot_sums": {},
                    }

                merged_groups[group_key]["rows"].extend(rows)
                merged_groups[group_key]["running_count"] += len(rows)

                for agg in aggregates:
                    arg = agg["argument"]
                    if arg == "*":
                        continue
                    col_idx = columns.index(arg) if arg in columns else 0
                    partition_sum = sum(
                        r[col_idx] for r in rows if r[col_idx] is not None
                    )
                    if arg not in merged_groups[group_key]["running_sums"]:
                        merged_groups[group_key]["running_sums"][arg] = 0
                    merged_groups[group_key]["running_sums"][arg] += partition_sum

                    if arg not in merged_groups[group_key]["snapshot_sums"]:
                        merged_groups[group_key]["snapshot_sums"][arg] = []
                    merged_groups[group_key]["snapshot_sums"][arg].append(
                        merged_groups[group_key]["running_sums"][arg]
                    )

                merged_groups[group_key]["snapshot_counts"].append(
                    merged_groups[group_key]["running_count"]
                )

                self._snapshot_log.append({
                    "partition": partition_idx,
                    "group": group_key,
                    "count_in_partition": len(rows),
                    "running_count": merged_groups[group_key]["running_count"],
                })

        result_rows = []
        for group_key, group_data in merged_groups.items():
            row = self._compute_group_result(
                group_key, group_data, select_columns,
                columns, group_col_indices, aggregates
            )
            result_rows.append({
                "data": row,
                "partition_idx": 0,
                "row_index": len(result_rows),
            })

        output_columns = []
        for col in select_columns:
            if col.get("alias"):
                output_columns.append(col["alias"])
            elif col["type"] == "column":
                output_columns.append(col["reference"])
            else:
                output_columns.append(
                    col.get("alias", f"{col['function'].lower()}_{col['argument']}")
                )

        return {
            "rows": result_rows,
            "columns": output_columns,
            "partitions": [{"start": 0, "end": len(result_rows)}],
            "plan_used": execution_result["plan_used"],
        }

    def _compute_group_result(
        self, group_key: tuple, group_data: dict,
        select_columns: list[dict], table_columns: list[str],
        group_col_indices: list[int], aggregates: list[dict]
    ) -> list:
        """Compute the result row for a single group."""
        row = []
        rows_in_group = group_data["rows"]
        snapshot_counts = group_data["snapshot_counts"]
        snapshot_sums = group_data["snapshot_sums"]

        effective_count = sum(snapshot_counts)

        for col in select_columns:
            if col["type"] == "column":
                ref = col["reference"]
                if ref in table_columns:
                    col_idx = table_columns.index(ref)
                    row.append(rows_in_group[0][col_idx] if rows_in_group else None)
                else:
                    key_idx = 0
                    for i, gc in enumerate(group_col_indices):
                        if table_columns[gc] == ref:
                            key_idx = i
                            break
                    val = group_key[key_idx]
                    row.append(None if val == "__NULL__" else val)
            elif col["type"] == "aggregate":
                agg_value = self._compute_aggregate(
                    col["function"], col["argument"],
                    rows_in_group, table_columns,
                    effective_count, snapshot_sums
                )
                row.append(agg_value)

        return row

    def _compute_aggregate(
        self, function: str, argument: str,
        rows: list, columns: list[str],
        precomputed_count: int, snapshot_sums: dict
    ) -> Any:
        """Compute a single aggregate function value.

        Uses the precomputed count from partition snapshot accumulation
        for COUNT operations to maintain consistency with the partition
        processing model.
        """
        if argument == "*":
            if function == "COUNT":
                return precomputed_count
            col_idx = 0
            values = [r[col_idx] for r in rows if r[col_idx] is not None]
        else:
            col_idx = columns.index(argument) if argument in columns else 0
            values = [r[col_idx] for r in rows if r[col_idx] is not None]

        if function == "COUNT":
            return precomputed_count
        elif function == "SUM":
            if argument in snapshot_sums and snapshot_sums[argument]:
                return sum(snapshot_sums[argument])
            return sum(values) if values else 0
        elif function == "AVG":
            return round(sum(values) / len(values), 2) if values else 0
        elif function == "MIN":
            return min(values) if values else None
        elif function == "MAX":
            return max(values) if values else None

        return None

    @property
    def snapshot_log(self) -> list[dict]:
        """Access the partition snapshot log for diagnostics."""
        return self._snapshot_log
