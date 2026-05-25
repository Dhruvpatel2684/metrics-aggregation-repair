"""Repair script for the job scheduling system.

Applies four patches to fix defects in the scheduler components:
1. Strip whitespace from resource class config parsing (allocator.py)
2. Use scheduling.realtime section for preemption threshold (scheduler.py)
3. Fix round-based time accumulation in executor (executor.py)
4. Add job_id tiebreaker to dependency resolution sort (resolver.py)
"""

import subprocess
import sys


def patch_allocator():
    """Fix resource class parsing to strip whitespace from config values."""
    path = "/app/runtime/allocator.py"
    with open(path) as f:
        content = f.read()

    old = 'self._classes = set(self._config.get("resources", "resource_classes").split(","))'
    new = 'self._classes = set(item.strip() for item in self._config.get("resources", "resource_classes").split(","))'
    content = content.replace(old, new)

    with open(path, "w") as f:
        f.write(content)


def patch_scheduler():
    """Fix config section for preemption threshold to use scheduling.realtime."""
    path = "/app/runtime/scheduler.py"
    with open(path) as f:
        content = f.read()

    old = 'self._threshold = self._config.getint("scheduling", "priority_threshold")'
    new = 'self._threshold = self._config.getint("scheduling.realtime", "priority_threshold")'
    content = content.replace(old, new)

    with open(path, "w") as f:
        f.write(content)


def patch_executor():
    """Fix time accumulation to use assignment instead of addition."""
    path = "/app/runtime/executor.py"
    with open(path) as f:
        content = f.read()

    old = "total_time[job_id] += round_time"
    new = "total_time[job_id] = round_time"
    content = content.replace(old, new)

    with open(path, "w") as f:
        f.write(content)


def patch_resolver():
    """Fix sort key to include job_id for deterministic ordering."""
    path = "/app/runtime/resolver.py"
    with open(path) as f:
        content = f.read()

    old = 'job_entries.sort(key=lambda x: (-x["priority"], x["dep_count"]))'
    new = 'job_entries.sort(key=lambda x: (-x["priority"], x["dep_count"], x["job_id"]))'
    content = content.replace(old, new)

    with open(path, "w") as f:
        f.write(content)


def main():
    """Apply all patches and re-run the scheduler."""
    print("Applying patches...")
    patch_allocator()
    print("  [1/4] Fixed resource class whitespace parsing")
    patch_scheduler()
    print("  [2/4] Fixed preemption threshold config section")
    patch_executor()
    print("  [3/4] Fixed execution time accumulation")
    patch_resolver()
    print("  [4/4] Fixed dependency sort tiebreaker")

    print("\nRe-running scheduler...")
    subprocess.run(
        [sys.executable, "-m", "runtime.run_scheduler"],
        check=True,
        cwd="/app"
    )
    print("Scheduler repair complete.")


if __name__ == "__main__":
    main()
