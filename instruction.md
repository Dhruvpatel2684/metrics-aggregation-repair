# Job Scheduler Repair Task

## Overview

A job scheduling system processes workload definitions, allocates compute resources, resolves execution dependencies, applies priority-based preemption, and produces an execution plan with a utilization report. The system is producing incorrect output across several dimensions. Your task is to identify and fix the defects.

## Environment

This task operates within a global system-wide tooling environment. All file paths referenced in this document are absolute paths within the runtime container.

### System Layout

| Path | Description |
|------|-------------|
| `/app/runtime/config/scheduler.ini` | Scheduler configuration |
| `/app/runtime/jobs/batch_workload.json` | Batch job definitions (20 jobs) |
| `/app/runtime/jobs/realtime_workload.json` | Real-time job definitions (10 jobs) |
| `/app/runtime/jobs/resource_manifest.json` | Available resource capacity |
| `/app/runtime/resolver.py` | Dependency resolution and ordering |
| `/app/runtime/allocator.py` | Resource allocation by class |
| `/app/runtime/scheduler.py` | Priority scheduling with preemption |
| `/app/runtime/executor.py` | Round-based execution simulation |
| `/app/runtime/export.py` | Output file generation |
| `/app/runtime/priority_queue.py` | Priority queue implementation |
| `/app/runtime/run_scheduler.py` | Main entry point |
| `/app/runtime/output/execution_plan.json` | Output: execution plan |
| `/app/runtime/output/schedule_report.json` | Output: schedule report |

### Entry Point

```bash
cd /app
python3 -m runtime.run_scheduler
```

## Processing Model

The system processes jobs through five sequential phases:

1. **Dependency Resolution** — Loads job definitions from workload files, computes the dependency graph, and sorts jobs into execution order by priority and dependency count. Jobs with identical priority and dependency count must be ordered deterministically by job identifier.

2. **Resource Allocation** — Assigns CPU, memory, GPU, and IO resources to each job based on its declared resource class. The allocator reads configured resource classes and applies the allocation strategy from the manifest.

3. **Priority Scheduling** — Enqueues jobs by priority and applies preemption rules. Jobs above the real-time priority threshold gain preemption rights, allowing them to interrupt lower-priority workloads.

4. **Execution Simulation** — Simulates job execution in configurable rounds (batch size from config). Computes execution timing based on allocated resources and scheduling overhead.

5. **Export** — Writes the execution plan and schedule report to JSON output files with an integrity hash for verification.

## Configuration

The configuration file at `/app/runtime/config/scheduler.ini` defines operational parameters:

- `[scheduling]` — General scheduling parameters (round size, concurrency limits)
- `[scheduling.realtime]` — Real-time scheduling thresholds for latency-sensitive workloads
- `[resources]` — Resource class definitions and allocation strategy
- `[execution]` — Timeout and retry configuration
- `[output]` — Output file names

## Input Data

### Job Definitions

Jobs are defined in two workload files:

- `batch_workload.json` — 20 batch processing jobs with varying priorities (1-10)
- `realtime_workload.json` — 10 real-time jobs with high priority (6-10)

Each job has:
- `job_id` (string): Unique identifier
- `name` (string): Human-readable name
- `resource_class` (string): One of `cpu_bound`, `memory_bound`, `io_bound`, `gpu_bound`
- `priority` (integer): Scheduling priority (1=lowest, 10=highest)
- `dependencies` (array of strings): Job IDs that must complete first
- `cpu_cores` (integer): Requested CPU cores
- `memory_gb` (integer): Requested memory in GB
- `estimated_time_ms` (integer): Estimated execution time

### Resource Manifest

Defines available system capacity:
- 16 CPU cores
- 64 GB RAM
- 4 GPU units
- 100 IO slots

## Output Schema

### execution_plan.json

```json
{
  "jobs": [
    {
      "job_id": "string",
      "name": "string",
      "resource_class": "string",
      "priority": "integer",
      "allocated_cpu": "integer",
      "allocated_memory": "integer",
      "allocated_gpu": "integer",
      "preemptible": "boolean",
      "execution_time_ms": "integer",
      "start_round": "integer",
      "status": "string"
    }
  ],
  "total_jobs": "integer",
  "scheduled_count": "integer",
  "gpu_jobs_allocated": "integer",
  "preemptible_count": "integer"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `jobs` | array | List of scheduled job entries |
| `jobs[].job_id` | string | Unique job identifier |
| `jobs[].name` | string | Job name |
| `jobs[].resource_class` | string | Resource classification |
| `jobs[].priority` | integer | Scheduling priority |
| `jobs[].allocated_cpu` | integer | Allocated CPU cores |
| `jobs[].allocated_memory` | integer | Allocated memory in GB |
| `jobs[].allocated_gpu` | integer | Allocated GPU units |
| `jobs[].preemptible` | boolean | Whether job has preemption rights |
| `jobs[].execution_time_ms` | integer | Computed execution time in milliseconds |
| `jobs[].start_round` | integer | Round in which execution begins |
| `jobs[].status` | string | Scheduling status |
| `total_jobs` | integer | Total number of jobs processed |
| `scheduled_count` | integer | Number of successfully scheduled jobs |
| `gpu_jobs_allocated` | integer | Number of jobs with GPU allocation |
| `preemptible_count` | integer | Number of jobs with preemption rights |

### schedule_report.json

```json
{
  "total_jobs_processed": "integer",
  "jobs_by_class": {
    "cpu_bound": "integer",
    "memory_bound": "integer",
    "io_bound": "integer",
    "gpu_bound": "integer"
  },
  "scheduling_rounds": "integer",
  "preemption_threshold": "integer",
  "gpu_allocations": "integer",
  "max_execution_time_ms": "integer",
  "execution_order": ["string"],
  "integrity_hash": "string"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_jobs_processed` | integer | Total jobs in the scheduling run |
| `jobs_by_class` | object | Count of jobs per resource class |
| `scheduling_rounds` | integer | Number of execution rounds |
| `preemption_threshold` | integer | Priority threshold for preemption |
| `gpu_allocations` | integer | Jobs that received GPU resources |
| `max_execution_time_ms` | integer | Maximum execution time across all jobs |
| `execution_order` | array of strings | Job IDs in execution sequence |
| `integrity_hash` | string | SHA-256 hash of execution results |

## Expected Behavior

When functioning correctly, the system should:

- Process all 30 jobs from both workload files
- Allocate GPU resources to all 4 `gpu_bound` jobs
- Use the real-time priority threshold (8) for preemption decisions
- Mark 12 jobs as preemptible (those with priority >= 8)
- Produce execution times not exceeding 5000ms for any job
- Order jobs with identical priority and dependency count deterministically by job identifier
- Generate a valid integrity hash matching the execution plan data

## Validation

Tests verify output correctness across multiple dimensions:
- File existence and structure
- Job count completeness
- Resource allocation coverage
- GPU resource assignment
- Execution time bounds
- Deterministic ordering
- Preemption configuration
- Preemptible job count
- Hash integrity
