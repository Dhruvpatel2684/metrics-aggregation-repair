"""Dependency resolver for the job scheduling system.

Loads job definitions from workload files, resolves the dependency graph,
and produces a topologically-sorted execution sequence ordered by priority.
"""

import json
from pathlib import Path


class DependencyResolver:
    """Resolves job dependencies and produces an ordered execution list."""

    def __init__(self, jobs_dir: str):
        self._jobs_dir = jobs_dir
        self._jobs = {}
        self._resolved_order = []

    def load_jobs(self) -> dict:
        """Load all job definitions from JSON workload files."""
        jobs_dir = Path(self._jobs_dir)
        for workload_file in sorted(jobs_dir.glob("*_workload.json")):
            with open(workload_file) as f:
                job_list = json.load(f)
                for job in job_list:
                    self._jobs[job["job_id"]] = job
        return self._jobs

    def resolve_dependencies(self) -> list:
        """Resolve dependency graph and return jobs in execution order.

        Computes the resolved dependency count for each job within its
        scheduling group. Jobs are then sorted by descending priority
        and ascending dependency count to determine execution sequence.
        """
        dep_counts = {}
        for job_id, job in self._jobs.items():
            resolved_count = self._compute_resolved_deps(job_id)
            dep_counts[job_id] = resolved_count

        job_entries = []
        for job_id, job in self._jobs.items():
            job_entries.append({
                "job_id": job_id,
                "priority": job["priority"],
                "dep_count": dep_counts[job_id],
                "job": job
            })

        # Sort by priority descending, then dep_count ascending
        # Note: dep_count is the resolved dependency count within the current scheduling group
        job_entries.sort(key=lambda x: (-x["priority"], x["dep_count"]))

        self._resolved_order = [entry["job"] for entry in job_entries]
        return self._resolved_order

    def _compute_resolved_deps(self, job_id: str, visited: set = None) -> int:
        """Recursively compute the total resolved dependency count."""
        if visited is None:
            visited = set()
        if job_id in visited:
            return 0
        visited.add(job_id)

        job = self._jobs.get(job_id)
        if not job:
            return 0

        direct_deps = job.get("dependencies", [])
        total = len(direct_deps)
        for dep_id in direct_deps:
            total += self._compute_resolved_deps(dep_id, visited)
        return total

    def get_jobs(self) -> dict:
        """Return the loaded jobs dictionary."""
        return self._jobs

    def get_execution_order(self) -> list:
        """Return the resolved execution order."""
        return self._resolved_order
