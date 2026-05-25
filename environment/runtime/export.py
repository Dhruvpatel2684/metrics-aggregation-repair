"""Export module for the job scheduling system.

Writes the execution plan and schedule report to JSON output files,
including an integrity hash for verification.
"""

import json
import hashlib
from pathlib import Path


class ScheduleExporter:
    """Exports scheduling results to JSON output files."""

    def __init__(self, output_dir: str):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def export_plan(self, results: list, gpu_count: int, preemptible_count: int) -> str:
        """Write the execution plan to execution_plan.json."""
        plan = {
            "jobs": results,
            "total_jobs": len(results),
            "scheduled_count": len(results),
            "gpu_jobs_allocated": gpu_count,
            "preemptible_count": preemptible_count
        }

        plan_path = self._output_dir / "execution_plan.json"
        with open(plan_path, "w") as f:
            json.dump(plan, f, indent=2)

        return str(plan_path)

    def export_report(self, results: list, rounds: int, threshold: int,
                      gpu_count: int, max_time: int) -> str:
        """Write the schedule report to schedule_report.json."""
        jobs_by_class = {}
        execution_order = []

        for job in results:
            rc = job["resource_class"]
            jobs_by_class[rc] = jobs_by_class.get(rc, 0) + 1
            execution_order.append(job["job_id"])

        report = {
            "total_jobs_processed": len(results),
            "jobs_by_class": jobs_by_class,
            "scheduling_rounds": rounds,
            "preemption_threshold": threshold,
            "gpu_allocations": gpu_count,
            "max_execution_time_ms": max_time,
            "execution_order": execution_order,
            "integrity_hash": self._compute_hash(results)
        }

        report_path = self._output_dir / "schedule_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        return str(report_path)

    def _compute_hash(self, results: list) -> str:
        """Compute SHA-256 integrity hash over the execution results."""
        hash_input = json.dumps(results, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(hash_input.encode()).hexdigest()
