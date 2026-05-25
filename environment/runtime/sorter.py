"""Result sorting module.

Applies ORDER BY specifications to query results, handling multi-column
sort keys with ascending/descending directions and stable tie-breaking
using row position metadata.
"""

from typing import Any


class ResultSorter:
    """Sorts query result sets according to ORDER BY specifications."""

    def sort(
        self, result: dict[str, Any], order_by: list[dict]
    ) -> dict[str, Any]:
        """Sort result rows according to the ORDER BY clause.

        For deterministic output, ties in the sort key are broken by
        the row's position index to ensure repeatable ordering across
        executions regardless of partition boundaries.
        """
        if not order_by:
            return result

        rows = result["rows"]
        columns = result["columns"]

        col_indices = []
        for order_spec in order_by:
            col_name = order_spec["column"]
            if "." in col_name:
                _, col_name = col_name.split(".", 1)
            if col_name in columns:
                col_indices.append(columns.index(col_name))
            else:
                for i, c in enumerate(columns):
                    if c.endswith(col_name) or col_name.endswith(c):
                        col_indices.append(i)
                        break
                else:
                    col_indices.append(0)

        directions = [
            spec.get("direction", "ASC") for spec in order_by
        ]

        def sort_key(item):
            """Build composite sort key from ORDER BY columns and tiebreaker."""
            row_data = item["data"]
            key_parts = []

            for idx, col_idx in enumerate(col_indices):
                value = row_data[col_idx]
                is_desc = directions[idx] == "DESC"

                if value is None:
                    sort_val = (1, 0)
                elif isinstance(value, (int, float)):
                    sort_val = (0, -value if is_desc else value)
                else:
                    sort_val = (0, value)
                    if is_desc:
                        sort_val = (0, _invert_string(value))

                key_parts.append(sort_val)

            # Tiebreaker: row_index reflects position within the processing partition
            key_parts.append(item["row_index"])
            return tuple(key_parts)

        sorted_rows = sorted(rows, key=sort_key)

        return {
            "rows": sorted_rows,
            "columns": result["columns"],
            "partitions": result["partitions"],
            "plan_used": result["plan_used"],
        }


def _invert_string(s: str) -> str:
    """Create an inverted string for descending string sort."""
    return "".join(chr(255 - ord(c)) if ord(c) < 256 else c for c in s)
