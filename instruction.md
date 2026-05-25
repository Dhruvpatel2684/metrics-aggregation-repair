# Connection State Recovery - Debugging Task

## Overview

A network monitoring system processes TCP connection lifecycle events from multiple gateway sources. The system sequences these events, tracks connection states through a finite state machine, manages a connection pool, and produces a recovery report summarizing the final state of all monitored connections.

The processing stages are:
1. **Sequencing** — Loading events from gateway JSONL files and sorting them into a global processing order
2. **Event Processing** — Applying events to connection state machines in batches, managing pool reservations
3. **Reconciliation** — Validating batch results, computing aggregate statistics, detecting anomalies
4. **Export** — Writing final connection states and a signed recovery report

## Problem

The recovery system is producing incorrect output. After processing all gateway events, the recovery report contains anomalies and connections are not reaching their expected terminal states. The system should process all 8 connections through their complete lifecycles (handshake, data transfer, graceful teardown) with zero anomalies in the final report.

## Environment

- **Language**: Python 3.11
- **Runtime files**: `/app/runtime/` (source code, config, event data, output directory)
- **Config**: `/app/runtime/config/connections.ini`
- **Event data**: `/app/runtime/events/*.jsonl` (4 gateway source files)
- **Output**: `/app/runtime/output/` (generated JSONL and JSON files)
- **Global system-wide tooling**: `uv` and `pytest` are available for running tests

## Task

Investigate and repair the runtime source files so that the connection state recovery system produces correct output. It is invoked via `python3 -m runtime.run_recovery` from the `/app` directory.

After repair, running the system should produce:
- All connections in CLOSED state
- Zero anomalies in the recovery report
- Pool fully released (0 active slots)
- Consistent integrity hash between the report and exported state data

## Output Schema

### connection_state.jsonl

Each line is a JSON record with fields:

| Field | Type | Description |
|-------|------|-------------|
| `conn_id` | string | Connection identifier |
| `state` | string | Final state (CLOSED for completed connections) |
| `transitions_count` | integer | Number of state transitions |
| `transition_history` | array | List of {from, to, event, timestamp} records |
| `source_addr` | string | Source IP:port |
| `dest_addr` | string | Destination IP:port |
| `created_at` | string | ISO-8601 creation timestamp |
| `last_transition_at` | string | ISO-8601 last transition timestamp |

### recovery_report.json

| Field | Type | Description |
|-------|------|-------------|
| `integrity_hash` | string | SHA-256 over sorted connection state lines |
| `total_connections` | integer | Number of connections processed |
| `state_distribution` | object | Count per final state |
| `pool_state` | object | Pool accounting (active_slots, reserved, confirmed, released) |
| `anomalies` | array | Detected anomalies (should be empty) |
| `transition_totals` | object | Per-connection transition counts |
| `batch_count` | integer | Number of processing batches |

## Key Files

| File | Purpose |
|------|---------|
| `runtime/sequencer.py` | Loads and orders events from gateway files |
| `runtime/handlers.py` | Processes events, manages connection state transitions |
| `runtime/event_processor.py` | Batch processing orchestration, pool management |
| `runtime/reconciler.py` | Validates results, computes statistics |
| `runtime/export.py` | Writes output files with integrity verification |
| `runtime/connection_pool.py` | Pool slot reservation and lifecycle |
| `runtime/state_machine.py` | TCP state transition definitions |
| `runtime/config/connections.ini` | Processing configuration parameters |
| `runtime/events/` | Gateway event source files (read-only data) |

## Notes

- Event data files are correct and should not be modified
- The state machine transition table is correct
- Configuration file format is standard INI
- Multiple interacting issues may exist across the processing stages
