"""Tests for the SQL query execution engine.

Validates query results, execution plans, and output integrity
for all configured queries against expected correct values.
"""

import hashlib
import json
import os

import pytest

OUTPUT_DIR = "/app/runtime/output"
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "execution_summary.json")


def load_result(query_id: str) -> dict:
    """Load a query result file from the output directory."""
    path = os.path.join(OUTPUT_DIR, f"{query_id}_result.json")
    with open(path, "r") as f:
        return json.load(f)


def load_summary() -> dict:
    """Load the execution summary."""
    with open(SUMMARY_FILE, "r") as f:
        return json.load(f)


class TestOutputFiles:
    """Verify that all expected output files are generated."""

    def test_output_files_exist(self):
        """All query result files and summary should exist."""
        assert os.path.isfile(SUMMARY_FILE), "execution_summary.json not found"
        for qid in ["q1", "q2", "q3", "q4"]:
            path = os.path.join(OUTPUT_DIR, f"{qid}_result.json")
            assert os.path.isfile(path), f"{qid}_result.json not found"

    def test_all_queries_executed(self):
        """Summary should report all 4 queries as successful."""
        summary = load_summary()
        assert summary["query_count"] == 4
        statuses = {q["id"]: q["status"] for q in summary["queries"]}
        for qid in ["q1", "q2", "q3", "q4"]:
            assert statuses.get(qid) == "success", f"Query {qid} not successful"


class TestQueryOne:
    """Tests for q1: simple join with filter."""

    def test_q1_simple_join_correct(self):
        """q1 should return employees with salary > 90000 joined with departments."""
        result = load_result("q1")
        names = sorted(row[0] for row in result["rows"])
        expected_names = sorted([
            "Alice", "Carol", "Eve", "Ivy", "Jack",
            "Kate", "Leo", "Quinn", "Rose", "Tina",
        ])
        assert names == expected_names
        assert result["row_count"] == 10


class TestQueryTwo:
    """Tests for q2: aggregate GROUP BY with NULL handling."""

    def test_q2_group_count(self):
        """q2 should produce 7 groups including NULL dept_id."""
        result = load_result("q2")
        assert result["row_count"] == 7, (
            f"Expected 7 groups (including NULL dept_id), got {result['row_count']}"
        )

    def test_q2_count_values(self):
        """q2 COUNT values should reflect actual row counts per group."""
        result = load_result("q2")
        counts_by_dept = {}
        for row in result["rows"]:
            dept_id = row[0]
            count = row[1]
            counts_by_dept[dept_id] = count

        assert counts_by_dept.get(1) == 4, f"dept 1 count: expected 4, got {counts_by_dept.get(1)}"
        assert counts_by_dept.get(2) == 4, f"dept 2 count: expected 4, got {counts_by_dept.get(2)}"
        assert counts_by_dept.get(3) == 4, f"dept 3 count: expected 4, got {counts_by_dept.get(3)}"
        assert counts_by_dept.get(4) == 2, f"dept 4 count: expected 2, got {counts_by_dept.get(4)}"
        assert counts_by_dept.get(5) == 2, f"dept 5 count: expected 2, got {counts_by_dept.get(5)}"
        assert counts_by_dept.get(6) == 2, f"dept 6 count: expected 2, got {counts_by_dept.get(6)}"
        assert counts_by_dept.get(None) == 2, f"NULL dept count: expected 2, got {counts_by_dept.get(None)}"


class TestQueryThree:
    """Tests for q3: join with sort-merge and salary ordering."""

    def test_q3_uses_sort_merge(self):
        """q3 execution plan should use sort_merge join method."""
        result = load_result("q3")
        plan = result.get("execution_plan", {})
        join_method = plan.get("join_method")
        assert join_method == "sort_merge", (
            f"Expected sort_merge join method, got {join_method}"
        )

    def test_q3_row_count(self):
        """q3 should return 14 rows (all employees in qualifying departments)."""
        result = load_result("q3")
        assert result["row_count"] == 14, (
            f"Expected 14 rows from join query, got {result['row_count']}"
        )

    def test_q3_result_order(self):
        """q3 results should be ordered by salary DESC with stable tie-breaking.

        When rows have identical ORDER BY values, the engine must preserve
        their original table insertion order (global row position across all
        partitions). Carol (row 3) should appear before Kate (row 11) and
        Tina (row 20) since all three have salary=92000.

        The sorter must use the global_row_index (assigned during table scan)
        not the partition-local row_index for tie-breaking.
        """
        result = load_result("q3")
        rows = result["rows"]

        salary_92k_rows = [r for r in rows if r[2] == 92000]
        assert len(salary_92k_rows) == 3, f"Expected 3 rows with salary 92000"

        names_92k = [r[0] for r in salary_92k_rows]
        assert names_92k == ["Carol", "Kate", "Tina"], (
            f"Salary 92000 tie-breaking order should be Carol, Kate, Tina "
            f"(by global table row position: row 3, row 11, row 20), "
            f"got {names_92k}. Check sorter.py tiebreaker key."
        )


class TestQueryFour:
    """Tests for q4: aggregate SUM with partition boundary."""

    def test_q4_sum_correct(self):
        """q4 SUM(salary) values should not be inflated by partition processing."""
        result = load_result("q4")
        sums_by_dept = {}
        for row in result["rows"]:
            sums_by_dept[row[0]] = row[1]

        assert sums_by_dept.get(1) == 371000, (
            f"dept 1 sum: expected 371000, got {sums_by_dept.get(1)}"
        )
        assert sums_by_dept.get(2) == 351000, (
            f"dept 2 sum: expected 351000, got {sums_by_dept.get(2)}"
        )
        assert sums_by_dept.get(3) == 364000, (
            f"dept 3 sum: expected 364000, got {sums_by_dept.get(3)}"
        )


class TestIntegrity:
    """Tests for output integrity verification."""

    def test_integrity_hash(self):
        """Execution summary hash should match recomputation from individual results."""
        summary = load_summary()
        recorded_hash = summary["integrity_hash"]

        hasher = hashlib.sha256()
        for qid in ["q1", "q2", "q3", "q4"]:
            result = load_result(qid)
            serialized = json.dumps(result["rows"], sort_keys=True, default=str)
            hasher.update(serialized.encode("utf-8"))

        expected_hash = hasher.hexdigest()
        assert recorded_hash == expected_hash, (
            f"Integrity hash mismatch: recorded={recorded_hash[:16]}..., "
            f"computed={expected_hash[:16]}..."
        )
