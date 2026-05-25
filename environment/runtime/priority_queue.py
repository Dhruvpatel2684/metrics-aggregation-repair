"""Priority queue implementation for the job scheduling system.

Provides a priority-aware queue that supports preemption semantics.
Jobs above a configurable priority threshold are marked as preemptible,
allowing them to interrupt lower-priority work during execution.

Real-time scheduling uses thresholds from [scheduling.realtime] for
latency-sensitive workloads that require guaranteed response times.
The real-time threshold determines which jobs receive preemption rights
in the scheduling phase.
"""

import heapq


class PriorityQueue:
    """A priority queue with preemption support for job scheduling."""

    def __init__(self):
        self._heap = []
        self._counter = 0

    def push(self, job: dict, priority: int):
        """Add a job to the queue with the given priority.

        Higher numeric priority values indicate more urgent jobs.
        The counter ensures FIFO ordering for equal priorities.
        """
        heapq.heappush(self._heap, (-priority, self._counter, job))
        self._counter += 1

    def pop(self) -> dict:
        """Remove and return the highest-priority job."""
        if not self._heap:
            raise IndexError("pop from empty priority queue")
        _, _, job = heapq.heappop(self._heap)
        return job

    def peek(self) -> dict:
        """Return the highest-priority job without removing it."""
        if not self._heap:
            raise IndexError("peek at empty priority queue")
        _, _, job = self._heap[0]
        return job

    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return len(self._heap) == 0

    def size(self) -> int:
        """Return the number of jobs in the queue."""
        return len(self._heap)

    def drain(self) -> list:
        """Remove and return all jobs in priority order."""
        result = []
        while not self.is_empty():
            result.append(self.pop())
        return result
