"""SQL query parser for the execution engine.

Extracts structured query representations from SQL-like query strings,
identifying tables, columns, join conditions, filters, aggregates, and
ordering clauses.
"""

import re
from typing import Any


def parse_query(sql: str) -> dict[str, Any]:
    """Parse a SQL query string into a structured representation.

    Returns a dictionary with keys:
        - select_columns: list of column references
        - tables: list of table definitions with aliases
        - joins: list of join conditions
        - filters: list of filter predicates
        - group_by: list of grouping columns (or None)
        - aggregates: list of aggregate functions
        - order_by: list of ordering specifications
        - method_hint: preferred join method if detectable from context
    """
    sql_normalized = " ".join(sql.split())

    result = {
        "select_columns": [],
        "tables": [],
        "joins": [],
        "filters": [],
        "group_by": None,
        "aggregates": [],
        "order_by": [],
        "method_hint": None,
    }

    select_match = re.search(
        r"SELECT\s+(.+?)\s+FROM", sql_normalized, re.IGNORECASE
    )
    if select_match:
        columns_str = select_match.group(1)
        result["select_columns"] = _parse_select_columns(columns_str)

    from_match = re.search(
        r"FROM\s+(\w+)\s+(\w+)", sql_normalized, re.IGNORECASE
    )
    if from_match:
        result["tables"].append({
            "name": from_match.group(1),
            "alias": from_match.group(2),
        })

    join_match = re.search(
        r"JOIN\s+(\w+)\s+(\w+)\s+ON\s+(.+?)(?:\s+WHERE|\s+GROUP|\s+ORDER|$)",
        sql_normalized,
        re.IGNORECASE,
    )
    if join_match:
        result["tables"].append({
            "name": join_match.group(1),
            "alias": join_match.group(2),
        })
        join_condition = join_match.group(3).strip()
        left_col, right_col = _parse_join_condition(join_condition)
        result["joins"].append({
            "left": left_col,
            "right": right_col,
            "type": "inner",
        })

    where_match = re.search(
        r"WHERE\s+(.+?)(?:\s+GROUP|\s+ORDER|$)",
        sql_normalized,
        re.IGNORECASE,
    )
    if where_match:
        result["filters"] = _parse_filters(where_match.group(1))

    group_match = re.search(
        r"GROUP\s+BY\s+(.+?)(?:\s+HAVING|\s+ORDER|$)",
        sql_normalized,
        re.IGNORECASE,
    )
    if group_match:
        cols = [c.strip() for c in group_match.group(1).split(",")]
        result["group_by"] = cols

    result["aggregates"] = _extract_aggregates(
        select_match.group(1) if select_match else ""
    )

    order_match = re.search(
        r"ORDER\s+BY\s+(.+)$", sql_normalized, re.IGNORECASE
    )
    if order_match:
        result["order_by"] = _parse_order_by(order_match.group(1))

    if result["joins"]:
        result["method_hint"] = "sort_merge"

    return result


def _parse_select_columns(columns_str: str) -> list[dict]:
    """Parse SELECT column list into structured form."""
    columns = []
    parts = _split_respecting_parens(columns_str)

    for part in parts:
        part = part.strip()
        alias_match = re.match(r"(.+?)\s+as\s+(\w+)", part, re.IGNORECASE)
        if alias_match:
            expr = alias_match.group(1).strip()
            alias = alias_match.group(2)
        else:
            expr = part
            alias = None

        agg_match = re.match(r"(COUNT|SUM|AVG|MIN|MAX)\s*\((.+)\)", expr, re.IGNORECASE)
        if agg_match:
            columns.append({
                "type": "aggregate",
                "function": agg_match.group(1).upper(),
                "argument": agg_match.group(2).strip(),
                "alias": alias or f"{agg_match.group(1).lower()}_{agg_match.group(2).strip()}",
            })
        else:
            columns.append({
                "type": "column",
                "reference": expr,
                "alias": alias,
            })

    return columns


def _split_respecting_parens(text: str) -> list[str]:
    """Split by comma but respect parentheses."""
    parts = []
    depth = 0
    current = []

    for char in text:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current))

    return parts


def _parse_join_condition(condition: str) -> tuple[str, str]:
    """Parse a join condition like 'e.dept_id = d.id' into (left, right)."""
    parts = condition.split("=")
    return parts[0].strip(), parts[1].strip()


def _parse_filters(filter_str: str) -> list[dict]:
    """Parse WHERE clause filters."""
    filters = []
    conditions = re.split(r"\s+AND\s+", filter_str, flags=re.IGNORECASE)

    for cond in conditions:
        cond = cond.strip()
        for op in [">=", "<=", "!=", ">", "<", "="]:
            if op in cond:
                parts = cond.split(op, 1)
                filters.append({
                    "column": parts[0].strip(),
                    "operator": op,
                    "value": parts[1].strip(),
                })
                break

    return filters


def _extract_aggregates(columns_str: str) -> list[dict]:
    """Extract aggregate function calls from SELECT."""
    aggregates = []
    for match in re.finditer(
        r"(COUNT|SUM|AVG|MIN|MAX)\s*\(([^)]+)\)", columns_str, re.IGNORECASE
    ):
        aggregates.append({
            "function": match.group(1).upper(),
            "argument": match.group(2).strip(),
        })
    return aggregates


def _parse_order_by(order_str: str) -> list[dict]:
    """Parse ORDER BY clause."""
    orders = []
    parts = order_str.split(",")

    for part in parts:
        part = part.strip()
        if part.upper().endswith(" DESC"):
            orders.append({
                "column": part[:-5].strip(),
                "direction": "DESC",
            })
        elif part.upper().endswith(" ASC"):
            orders.append({
                "column": part[:-4].strip(),
                "direction": "ASC",
            })
        else:
            orders.append({
                "column": part,
                "direction": "ASC",
            })

    return orders
