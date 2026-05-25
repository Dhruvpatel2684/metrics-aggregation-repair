"""Validation tests for the job scheduling system.

Tests verify correct resource allocation, preemption configuration,
execution timing, dependency ordering, and output integrity.
"""

import json
import hashlib
import os

import pytest


OUTPUT_DIR = "/app/runtime/output"
PLAN_PATH = os.path.join(OUTPUT_DIR, "execution_plan.json")
REPORT_PATH = os.path.join(OUTPUT_DIR, "schedule_report.json")


@pytest.fixture
def execution_plan():
    """Load the execution plan output."""
    with open(PLAN_PATH) as f:
        return json.load(f)


@pytest.fixture
def schedule_report():
    """Load the schedule report output."""
    with open(REPORT_PATH) as f:
        return json.load(f)


# === Easy Tests (always pass) ===

class TestOutputBasics:
    """Basic output validation tests."""

    def test_output_files_exist(self):
        """Verify both output files were created."""
        assert os.path.isfile(PLAN_PATH), "execution_plan.json not found"
        assert os.path.isfile(REPORT_PATH), "schedule_report.json not found"

    def test_all_jobs_present(self, execution_plan):
        """Verify all 30 jobs are present in the execution plan."""
        assert execution_plan["total_jobs"] == 30
        assert execution_plan["scheduled_count"] == 30
        assert len(execution_plan["jobs"]) == 30

    def test_report_structure(self, schedule_report):
        """Verify required fields exist in the schedule report."""
        required_fields = [
            "total_jobs_processed",
            "jobs_by_class",
            "scheduling_rounds",
            "preemption_threshold",
            "gpu_allocations",
            "max_execution_time_ms",
            "execution_order",
            "integrity_hash"
        ]
        for field in required_fields:
            assert field in schedule_report, f"Missing field: {field}"

    def test_jobs_have_allocations(self, execution_plan):
        """Verify all jobs have CPU allocation greater than zero."""
        for job in execution_plan["jobs"]:
            assert job["allocated_cpu"] > 0, (
                f"Job {job['job_id']} has zero CPU allocation"
            )


# === Medium Tests (pass with 1-2 fixes) ===

class TestResourceAllocation:
    """Resource allocation validation tests."""

    def test_gpu_jobs_allocated(self, schedule_report):
        """Verify GPU jobs received proper resource allocation.

        The system should allocate GPU resources to all gpu_bound jobs.
        Expected: 4 GPU allocations for gpu_bound workloads.
        """
        assert schedule_report["gpu_allocations"] == 4, (
            f"Expected 4 GPU allocations, got {schedule_report['gpu_allocations']}. "
            "Check resource class parsing in /app/runtime/allocator.py"
        )

    def test_no_inflated_times(self, schedule_report):
        """Verify execution times are within expected bounds.

        No job should exceed 5000ms execution time under normal
        scheduling conditions with proper round-based computation.
        """
        max_time = schedule_report["max_execution_time_ms"]
        assert max_time <= 5000, (
            f"Max execution time {max_time}ms exceeds 5000ms limit. "
            "Check round-based time computation in /app/runtime/executor.py"
        )

    def test_job_012_before_015(self, schedule_report):
        """Verify deterministic ordering of jobs with equal priority.

        Jobs with identical priority and dependency count must be ordered
        deterministically by job identifier.
        Hint: check dependency sort tiebreaker in /app/runtime/resolver.py
        """
        order = schedule_report["execution_order"]
        idx_012 = order.index("job_012")
        idx_015 = order.index("job_015")
        assert idx_012 < idx_015, (
            f"job_012 (index {idx_012}) should appear before job_015 (index {idx_015}). "
            "Jobs with same priority and dep_count need deterministic tiebreaker"
        )


# === Hard Tests (need 3-4 fixes) ===

class TestPreemption:
    """Preemption configuration validation tests."""

    def test_preemption_threshold(self, schedule_report):
        """Verify the preemption threshold uses real-time configuration.

        The scheduling system should use the real-time priority threshold
        for latency-sensitive workload preemption decisions.
        Expected gpu_allocations=4 and preemption_threshold=8.
        """
        assert schedule_report["preemption_threshold"] == 8, (
            f"Expected threshold 8, got {schedule_report['preemption_threshold']}. "
            "Check which config section is used in /app/runtime/scheduler.py"
        )
        assert schedule_report["gpu_allocations"] == 4, (
            f"Expected 4 GPU allocations with correct threshold, "
            f"got {schedule_report['gpu_allocations']}"
        )

    def test_preemptible_count(self, execution_plan, schedule_report):
        """Verify correct number of preemptible jobs.

        With threshold=8, jobs with priority >= 8 receive preemption rights.
        Expected: 12 preemptible jobs across both workloads, with execution
        times within bounds and correct GPU allocation.
        """
        assert execution_plan["preemptible_count"] == 12, (
            f"Expected 12 preemptible jobs, got {execution_plan['preemptible_count']}. "
            "Preemption threshold and job priorities determine preemptible count"
        )
        assert schedule_report["max_execution_time_ms"] <= 5000, (
            f"Preemptible job timing exceeds bounds: "
            f"{schedule_report['max_execution_time_ms']}ms"
        )

    def test_integrity_hash(self, execution_plan, schedule_report):
        """Verify the integrity hash matches recomputation.

        The hash must be consistent with the actual execution results,
        confirming no data corruption during the scheduling process.
        Requires all scheduling components to produce correct output.
        """
        results = execution_plan["jobs"]
        hash_input = json.dumps(results, sort_keys=True, separators=(",", ":"))
        expected_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        assert schedule_report["integrity_hash"] == expected_hash, (
            "Integrity hash mismatch: report hash does not match "
            "recomputed hash from execution plan data"
        )
        # Verify hash is computed over correctly-ordered data
        order = schedule_report["execution_order"]
        idx_012 = order.index("job_012")
        idx_015 = order.index("job_015")
        assert idx_012 < idx_015, (
            "Hash computed over incorrectly ordered data: "
            "job_012 must precede job_015"
        )
