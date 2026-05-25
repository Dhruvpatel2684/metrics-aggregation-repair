"""Query executor module.

Processes execution plans by loading table data, applying filters,
performing joins, and coordinating partition-based processing for
memory-efficient query evaluation.
"""

import configparser
import json
import os
from typing import Any


class QueryExecutor:
    """Executes query plans against table data using partition-based processing."""

    def __init__(self, config: configparser.ConfigParser):
        self._config = config
        self._data_dir = config.get("engine", "data_directory")
        self._partition_size = config.getint("engine", "partition_size")
        self._null_handling = config.get("executor", "null_handling")
        self._tables_cache: dict[str, dict] = {}

    def execute(self, plan: dict[str, Any], parsed_query: dict[str, Any]) -> dict[str, Any]:
        """Execute a query plan and return partitioned results.

        Returns a dictionary containing:
            - rows: list of result rows
            - columns: list of column names
            - partitions: partition metadata for downstream processing
            - plan_used: the execution plan that was applied
        """
        tables_needed = [
            stage["table"] for stage in plan["stages"] if stage["type"] == "scan"
        ]
        for table_name in tables_needed:
            self._load_table(table_name)

        if parsed_query["group_by"]:
            return self._execute_aggregate_query(plan, parsed_query)
        elif parsed_query["joins"]:
            return self._execute_join_query(plan, parsed_query)
        else:
            return self._execute_simple_query(plan, parsed_query)

    def _load_table(self, table_name: str) -> None:
        """Load table data from JSON file into cache."""
        if table_name in self._tables_cache:
            return

        file_path = os.path.join(self._data_dir, f"{table_name}.json")
        with open(file_path, "r") as f:
            self._tables_cache[table_name] = json.load(f)

    def _execute_simple_query(
        self, plan: dict[str, Any], parsed_query: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a query without joins or aggregation."""
        table_info = parsed_query["tables"][0]
        table_data = self._tables_cache[table_info["name"]]
        columns = table_data["columns"]
        rows = table_data["rows"]

        filtered = self._apply_filters(rows, columns, parsed_query["filters"], table_info["alias"])

        return {
            "rows": filtered,
            "columns": columns,
            "partitions": [{"start": 0, "end": len(filtered)}],
            "plan_used": plan,
        }

    def _execute_join_query(
        self, plan: dict[str, Any], parsed_query: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a join query with partition-based processing."""
        left_table_info = parsed_query["tables"][0]
        right_table_info = parsed_query["tables"][1]
        left_data = self._tables_cache[left_table_info["name"]]
        right_data = self._tables_cache[right_table_info["name"]]

        join_info = parsed_query["joins"][0]
        join_method = plan["join_method"]

        left_col_ref = join_info["left"]
        right_col_ref = join_info["right"]
        left_join_col = self._resolve_column_index(
            left_col_ref, left_data["columns"], left_table_info["alias"]
        )
        right_join_col = self._resolve_column_index(
            right_col_ref, right_data["columns"], right_table_info["alias"]
        )

        all_results = []
        partition_metadata = []
        partition_idx = 0

        for start in range(0, len(left_data["rows"]), self._partition_size):
            end = min(start + self._partition_size, len(left_data["rows"]))
            left_partition = left_data["rows"][start:end]

            if join_method == "sort_merge":
                joined = self._sort_merge_join(
                    left_partition, right_data["rows"],
                    left_join_col, right_join_col
                )
            elif join_method == "hash_join":
                joined = self._hash_join(
                    left_partition, right_data["rows"],
                    left_join_col, right_join_col
                )
            else:
                joined = self._nested_loop_join(
                    left_partition, right_data["rows"],
                    left_join_col, right_join_col
                )

            filtered = self._apply_join_filters(
                joined, parsed_query["filters"],
                left_data["columns"], right_data["columns"],
                left_table_info["alias"], right_table_info["alias"]
            )

            for row_idx, row in enumerate(filtered):
                all_results.append({
                    "data": row,
                    "partition_idx": partition_idx,
                    "row_index": row_idx,
                })

            partition_metadata.append({
                "start": start,
                "end": end,
                "result_count": len(filtered),
            })
            partition_idx += 1

        output_columns = self._build_output_columns(
            parsed_query["select_columns"],
            left_data["columns"], right_data["columns"],
            left_table_info["alias"], right_table_info["alias"]
        )

        projected_results = []
        for item in all_results:
            projected_row = self._project_join_row(
                item["data"], parsed_query["select_columns"],
                left_data["columns"], right_data["columns"],
                left_table_info["alias"], right_table_info["alias"]
            )
            projected_results.append({
                "data": projected_row,
                "partition_idx": item["partition_idx"],
                "row_index": item["row_index"],
            })

        return {
            "rows": projected_results,
            "columns": output_columns,
            "partitions": partition_metadata,
            "plan_used": plan,
        }

    def _execute_aggregate_query(
        self, plan: dict[str, Any], parsed_query: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute an aggregate query with partition-based processing.

        Uses the configured NULL handling semantics to determine whether
        rows with NULL values in GROUP BY columns form their own group.
        """
        table_info = parsed_query["tables"][0]
        table_data = self._tables_cache[table_info["name"]]
        columns = table_data["columns"]
        rows = table_data["rows"]

        group_cols = parsed_query["group_by"]
        group_col_indices = [columns.index(col) for col in group_cols]

        partition_results = []
        partition_metadata = []

        for start in range(0, len(rows), self._partition_size):
            end = min(start + self._partition_size, len(rows))
            partition = rows[start:end]

            groups: dict[Any, list] = {}
            for row in partition:
                key = tuple(row[i] for i in group_col_indices)

                has_null = any(v is None for v in key)
                if has_null and self._null_handling == "skip":
                    continue

                hashable_key = tuple(
                    "__NULL__" if v is None else v for v in key
                )
                if hashable_key not in groups:
                    groups[hashable_key] = []
                groups[hashable_key].append(row)

            partition_results.append(groups)
            partition_metadata.append({"start": start, "end": end})

        return {
            "partition_groups": partition_results,
            "columns": columns,
            "group_cols": group_cols,
            "aggregates": parsed_query["aggregates"],
            "select_columns": parsed_query["select_columns"],
            "partitions": partition_metadata,
            "plan_used": plan,
        }

    def _sort_merge_join(
        self, left_rows: list, right_rows: list,
        left_col: int, right_col: int
    ) -> list[tuple]:
        """Perform a sort-merge join between two row sets.

        Both sides are sorted by the join column, then merged by walking
        through both sorted sequences simultaneously.
        """
        left_sorted = sorted(left_rows, key=lambda r: (r[left_col] is None, r[left_col]))
        right_sorted = sorted(right_rows, key=lambda r: (r[right_col] is None, r[right_col]))

        results = []
        r_idx = 0

        for left_row in left_sorted:
            left_val = left_row[left_col]
            if left_val is None:
                continue

            while r_idx < len(right_sorted) and (
                right_sorted[r_idx][right_col] is None
                or right_sorted[r_idx][right_col] < left_val
            ):
                r_idx += 1

            temp_idx = r_idx
            while temp_idx < len(right_sorted) and right_sorted[temp_idx][right_col] == left_val:
                results.append((left_row, right_sorted[temp_idx]))
                temp_idx += 1

        return results

    def _hash_join(
        self, left_rows: list, right_rows: list,
        left_col: int, right_col: int
    ) -> list[tuple]:
        """Perform a hash join using the right table as build side."""
        hash_table: dict[Any, list] = {}
        for row in right_rows:
            key = row[right_col]
            if key is None:
                continue
            if key not in hash_table:
                hash_table[key] = []
            hash_table[key].append(row)

        results = []
        for left_row in left_rows:
            left_val = left_row[left_col]
            if left_val is None:
                continue
            if left_val in hash_table:
                for right_row in hash_table[left_val]:
                    results.append((left_row, right_row))

        return results

    def _nested_loop_join(
        self, left_rows: list, right_rows: list,
        left_col: int, right_col: int
    ) -> list[tuple]:
        """Perform a nested loop join (preserves left-table row order)."""
        results = []
        for left_row in left_rows:
            left_val = left_row[left_col]
            if left_val is None:
                continue
            for right_row in right_rows:
                if right_row[right_col] == left_val:
                    results.append((left_row, right_row))
        return results

    def _apply_filters(
        self, rows: list, columns: list[str],
        filters: list[dict], alias: str
    ) -> list:
        """Apply filter predicates to rows."""
        if not filters:
            return rows

        result = []
        for row in rows:
            if self._row_matches_filters(row, columns, filters, alias):
                result.append(row)
        return result

    def _apply_join_filters(
        self, joined_rows: list[tuple], filters: list[dict],
        left_columns: list[str], right_columns: list[str],
        left_alias: str, right_alias: str
    ) -> list[tuple]:
        """Apply filters to joined row pairs."""
        if not filters:
            return joined_rows

        result = []
        for left_row, right_row in joined_rows:
            passes = True
            for filt in filters:
                col_ref = filt["column"]
                if "." in col_ref:
                    tbl_alias, col_name = col_ref.split(".", 1)
                    if tbl_alias == left_alias:
                        col_idx = left_columns.index(col_name)
                        value = left_row[col_idx]
                    else:
                        col_idx = right_columns.index(col_name)
                        value = right_row[col_idx]
                else:
                    if col_ref in left_columns:
                        col_idx = left_columns.index(col_ref)
                        value = left_row[col_idx]
                    else:
                        col_idx = right_columns.index(col_ref)
                        value = right_row[col_idx]

                if not self._evaluate_predicate(value, filt["operator"], filt["value"]):
                    passes = False
                    break

            if passes:
                result.append((left_row, right_row))

        return result

    def _row_matches_filters(
        self, row: list, columns: list[str],
        filters: list[dict], alias: str
    ) -> bool:
        """Check if a row matches all filter predicates."""
        for filt in filters:
            col_ref = filt["column"]
            if "." in col_ref:
                _, col_name = col_ref.split(".", 1)
            else:
                col_name = col_ref

            if col_name in columns:
                col_idx = columns.index(col_name)
                value = row[col_idx]
                if not self._evaluate_predicate(value, filt["operator"], filt["value"]):
                    return False

        return True

    def _evaluate_predicate(self, value: Any, operator: str, threshold: str) -> bool:
        """Evaluate a single filter predicate."""
        if value is None:
            return False

        try:
            threshold_val = float(threshold) if threshold.replace(".", "").replace("-", "").isdigit() else threshold
        except (ValueError, AttributeError):
            threshold_val = threshold

        if isinstance(value, (int, float)) and isinstance(threshold_val, (int, float)):
            if operator == ">":
                return value > threshold_val
            elif operator == ">=":
                return value >= threshold_val
            elif operator == "<":
                return value < threshold_val
            elif operator == "<=":
                return value <= threshold_val
            elif operator == "=":
                return value == threshold_val
            elif operator == "!=":
                return value != threshold_val

        return str(value) == str(threshold_val)

    def _resolve_column_index(
        self, col_ref: str, columns: list[str], alias: str
    ) -> int:
        """Resolve a column reference like 'e.dept_id' to a column index."""
        if "." in col_ref:
            _, col_name = col_ref.split(".", 1)
        else:
            col_name = col_ref
        return columns.index(col_name)

    def _build_output_columns(
        self, select_columns: list[dict],
        left_columns: list[str], right_columns: list[str],
        left_alias: str, right_alias: str
    ) -> list[str]:
        """Build output column names from SELECT clause."""
        output = []
        for col in select_columns:
            if col.get("alias"):
                output.append(col["alias"])
            else:
                output.append(col["reference"])
        return output

    def _project_join_row(
        self, row_pair: tuple, select_columns: list[dict],
        left_columns: list[str], right_columns: list[str],
        left_alias: str, right_alias: str
    ) -> list:
        """Project selected columns from a joined row pair."""
        left_row, right_row = row_pair
        result = []

        for col in select_columns:
            if col["type"] == "aggregate":
                result.append(None)
                continue

            ref = col["reference"]
            if "." in ref:
                tbl_alias, col_name = ref.split(".", 1)
                if tbl_alias == left_alias:
                    idx = left_columns.index(col_name)
                    result.append(left_row[idx])
                else:
                    idx = right_columns.index(col_name)
                    result.append(right_row[idx])
            else:
                if ref in left_columns:
                    idx = left_columns.index(ref)
                    result.append(left_row[idx])
                elif ref in right_columns:
                    idx = right_columns.index(ref)
                    result.append(right_row[idx])
                else:
                    result.append(None)

        return result
