"""Job scheduler with preemption support.

Manages the scheduling of jobs into execution slots, applying priority-based
preemption rules to ensure high-priority jobs receive timely execution.
"""

import configparser
from .priority_queue import PriorityQueue


class JobScheduler:
    """Schedules jobs with priority-based preemption."""

    def __init__(self, config_path: str):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._threshold = self._config.getint("scheduling", "priority_threshold")
        self._max_concurrent = self._config.getint("scheduling", "max_concurrent")
        self._queue = PriorityQueue()
        self._scheduled = []

    def schedule(self, jobs: list, allocations: dict) -> list:
        """Schedule jobs applying preemption rules.

        Jobs with priority at or above the configured threshold receive
        preemption rights, allowing them to interrupt lower-priority work.
        """
        for job in jobs:
            self._queue.push(job, job["priority"])

        while not self._queue.is_empty():
            job = self._queue.pop()
            job_id = job["job_id"]
            allocation = allocations.get(job_id, {})

            preemptible = job["priority"] >= self._threshold
            scheduled_entry = {
                "job_id": job_id,
                "name": job["name"],
                "resource_class": job["resource_class"],
                "priority": job["priority"],
                "dependencies": job.get("dependencies", []),
                "allocated_cpu": allocation.get("allocated_cpu", 0),
                "allocated_memory": allocation.get("allocated_memory", 0),
                "allocated_gpu": allocation.get("allocated_gpu", 0),
                "preemptible": preemptible,
                "status": "scheduled"
            }
            self._scheduled.append(scheduled_entry)

        return self._scheduled

    def get_threshold(self) -> int:
        """Return the preemption priority threshold."""
        return self._threshold

    def get_preemptible_count(self) -> int:
        """Return the count of jobs with preemption rights."""
        return sum(1 for job in self._scheduled if job.get("preemptible"))

    def get_scheduled(self) -> list:
        """Return the list of scheduled job entries."""
        return self._scheduled
