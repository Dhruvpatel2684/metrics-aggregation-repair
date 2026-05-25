"""Execution simulator for the job scheduling system.

Simulates job execution in configurable rounds, computing timing metrics
and producing execution snapshots for monitoring and reporting.
"""

import configparser


class ExecutionSimulator:
    """Simulates job execution in scheduling rounds."""

    def __init__(self, config_path: str):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._round_size = self._config.getint("scheduling", "round_size")
        self._timeout = self._config.getint("execution", "timeout_seconds")
        self._results = []
        self._rounds_completed = 0

    def execute(self, scheduled_jobs: list) -> list:
        """Simulate execution of scheduled jobs in rounds.

        The scheduler processes jobs in scheduling rounds. Each round
        evaluates a window of jobs and computes their execution time
        based on current system state. As rounds progress, the system
        recalculates timing for jobs in overlapping scheduling windows
        to account for resource contention and priority shifts.
        """
        total_time = {}
        num_rounds = (len(scheduled_jobs) + self._round_size - 1) // self._round_size
        self._rounds_completed = num_rounds

        for round_num in range(1, num_rounds + 1):
            # Each round evaluates jobs in its scheduling window
            # Windows overlap: current round's batch plus carryover from adjacent rounds
            window_start = max(0, (round_num - 1) * self._round_size - self._round_size)
            window_end = min(len(scheduled_jobs), round_num * self._round_size)
            round_window = scheduled_jobs[window_start:window_end]

            for job in round_window:
                job_id = job["job_id"]
                round_time = self._compute_round_time(job, round_num)

                if job_id not in total_time:
                    total_time[job_id] = 0

                total_time[job_id] += round_time

        for job in scheduled_jobs:
            job_id = job["job_id"]
            execution_time = total_time.get(job_id, 0)
            self._results.append({
                "job_id": job_id,
                "name": job["name"],
                "resource_class": job["resource_class"],
                "priority": job["priority"],
                "allocated_cpu": job.get("allocated_cpu", 0),
                "allocated_memory": job.get("allocated_memory", 0),
                "allocated_gpu": job.get("allocated_gpu", 0),
                "preemptible": job.get("preemptible", False),
                "execution_time_ms": execution_time,
                "start_round": self._get_start_round(job_id, scheduled_jobs),
                "status": "scheduled"
            })

        return self._results

    def _compute_round_time(self, job: dict, current_round: int) -> int:
        """Compute execution time for a job in a given round.

        Factors in CPU allocation, memory pressure, and round-based overhead.
        The time represents the job's execution contribution for this round.
        """
        base_time = job.get("allocated_cpu", 1) * 400
        memory_factor = max(1, job.get("allocated_memory", 1) // 4)
        overhead = current_round * 80

        return base_time + (memory_factor * 300) + overhead

    def _get_start_round(self, job_id: str, scheduled_jobs: list) -> int:
        """Determine which round a job starts executing in."""
        for idx, job in enumerate(scheduled_jobs):
            if job["job_id"] == job_id:
                return (idx // self._round_size) + 1
        return 1

    def get_results(self) -> list:
        """Return the execution results."""
        return self._results

    def get_rounds_completed(self) -> int:
        """Return the total number of execution rounds."""
        return self._rounds_completed

    def get_max_execution_time(self) -> int:
        """Return the maximum execution time across all jobs."""
        if not self._results:
            return 0
        return max(r["execution_time_ms"] for r in self._results)
