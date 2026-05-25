"""Resource allocator for the job scheduling system.

Assigns CPU, memory, GPU, and IO resources to jobs based on their
resource class and the available system capacity defined in the manifest.
"""

import json
import configparser


class ResourceAllocator:
    """Allocates system resources to scheduled jobs based on resource class."""

    def __init__(self, config_path: str, manifest_path: str):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._manifest = self._load_manifest(manifest_path)
        self._classes = set(self._config.get("resources", "resource_classes").split(","))
        self._strategy = self._config.get("resources", "allocation_strategy")
        self._overcommit = self._config.getfloat("resources", "overcommit_ratio")
        self._allocations = {}

    def _load_manifest(self, manifest_path: str) -> dict:
        """Load the resource manifest defining available capacity."""
        with open(manifest_path) as f:
            return json.load(f)

    def allocate(self, jobs: list) -> dict:
        """Allocate resources to each job based on its resource class.

        Jobs whose resource_class is not in the configured set receive
        zero allocation and are marked with allocation_status=skipped.
        """
        defaults = self._manifest.get("resource_class_defaults", {})
        available = self._manifest.get("available_resources", {})

        for job in jobs:
            job_id = job["job_id"]
            resource_class = job["resource_class"]

            if resource_class not in self._classes:
                self._allocations[job_id] = {
                    "allocated_cpu": job.get("cpu_cores", 1),
                    "allocated_memory": job.get("memory_gb", 1),
                    "allocated_gpu": 0,
                    "allocated_io": 0,
                    "allocation_status": "degraded"
                }
                continue

            class_defaults = defaults.get(resource_class, {})
            cpu = min(job.get("cpu_cores", class_defaults.get("cpu_cores", 1)),
                      available.get("cpu_cores", 16))
            memory = min(job.get("memory_gb", class_defaults.get("memory_gb", 4)),
                         available.get("memory_gb", 64))
            gpu = class_defaults.get("gpu_units", 0)
            io = class_defaults.get("io_slots", 5)

            if self._strategy == "best_fit":
                cpu = int(cpu * self._overcommit)
                memory = int(memory * self._overcommit)

            self._allocations[job_id] = {
                "allocated_cpu": max(cpu, 1),
                "allocated_memory": max(memory, 1),
                "allocated_gpu": gpu,
                "allocated_io": io,
                "allocation_status": "allocated"
            }

        return self._allocations

    def get_allocations(self) -> dict:
        """Return the computed allocations dictionary."""
        return self._allocations

    def get_gpu_allocation_count(self) -> int:
        """Return the number of jobs that received GPU resources."""
        return sum(1 for alloc in self._allocations.values()
                   if alloc.get("allocated_gpu", 0) > 0)
