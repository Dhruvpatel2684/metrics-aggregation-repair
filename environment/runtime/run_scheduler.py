"""Main entry point for the job scheduling system.

Orchestrates the scheduling workflow: dependency resolution, resource
allocation, priority scheduling, execution simulation, and export.
"""

import os

from .resolver import DependencyResolver
from .allocator import ResourceAllocator
from .scheduler import JobScheduler
from .executor import ExecutionSimulator
from .export import ScheduleExporter


def main():
    """Run the complete scheduling workflow."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "scheduler.ini")
    jobs_dir = os.path.join(base_dir, "jobs")
    manifest_path = os.path.join(jobs_dir, "resource_manifest.json")
    output_dir = os.path.join(base_dir, "output")

    # Phase 1: Resolve dependencies and determine execution order
    resolver = DependencyResolver(jobs_dir)
    resolver.load_jobs()
    ordered_jobs = resolver.resolve_dependencies()

    # Phase 2: Allocate resources based on job resource classes
    allocator = ResourceAllocator(config_path, manifest_path)
    allocations = allocator.allocate(ordered_jobs)

    # Phase 3: Schedule with preemption support
    scheduler = JobScheduler(config_path)
    scheduled = scheduler.schedule(ordered_jobs, allocations)

    # Phase 4: Simulate execution in rounds
    executor = ExecutionSimulator(config_path)
    results = executor.execute(scheduled)

    # Phase 5: Export execution plan and report
    exporter = ScheduleExporter(output_dir)
    exporter.export_plan(
        results,
        gpu_count=allocator.get_gpu_allocation_count(),
        preemptible_count=scheduler.get_preemptible_count()
    )
    exporter.export_report(
        results,
        rounds=executor.get_rounds_completed(),
        threshold=scheduler.get_threshold(),
        gpu_count=allocator.get_gpu_allocation_count(),
        max_time=executor.get_max_execution_time()
    )

    print(f"Scheduling complete: {len(results)} jobs processed")
    print(f"Output written to: {output_dir}")


if __name__ == "__main__":
    main()
