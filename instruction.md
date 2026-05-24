# Connection State Recovery — Operational Context

## Situation

A TCP connection state recovery runtime replays event logs from multiple network gateways through a multi-phase processing sequence to reconstruct connection lifecycle states. The system normalizes timestamps across sources, validates event sequences, processes events through a state machine with connection pool management, reconciles results across processing batches, and exports a final recovery snapshot.

After a configuration change to onboard a new gateway source, the recovery output exhibits several anomalies that violate connection lifecycle invariants.

## Observed Symptoms

Running `python3 /app/runtime/run_recovery.py` produces output with the following issues:

- Multiple connections remain stuck in intermediate half-closed states instead of completing their teardown lifecycle
- The connection pool reports leaked slot reservations that were never confirmed or swept
- Transition counts for some connections appear inflated beyond what the event data justifies
- The pool accounting shows more active slots than there are non-closed connections
- Both active-close and passive-close scenarios appear to produce identical intermediate states

## Expected Behavior

After repair, the recovery output must show:
- All connections with complete close sequences (FIN_RECV + CLOSE + TIMEOUT) reach CLOSED state
- Pool slot reservations are either confirmed (on ESTABLISHED) or swept (on timeout)
- Transition counts reflect actual transitions without inflation from batch processing
- Both HALF_CLOSED_LOCAL (active close) and HALF_CLOSED_REMOTE (passive close) appear in output
- Pool active count matches the number of non-CLOSED connections exactly

## Environment

The runtime environment contains system-wide Python tooling and pytest installation.

## Key Files

- `/app/runtime/run_recovery.py` — orchestration entrypoint
- `/app/runtime/sequencer.py` — timestamp normalization and event merge-sort
- `/app/runtime/event_processor.py` — sequence validation, deduplication, batching
- `/app/runtime/state_machine.py` — TCP state transition logic with half-close support
- `/app/runtime/connection_pool.py` — two-phase slot management (reserve/confirm/release)
- `/app/runtime/handlers.py` — event dispatch and state/pool coordination
- `/app/runtime/reconciler.py` — batch result merging, stale sweep, cross-source dedup
- `/app/runtime/export.py` — snapshot and report generation
- `/app/runtime/config/connections.ini` — pool parameters, timeouts, epoch offsets
- `/app/runtime/events/` — JSONL event logs from four gateway sources
- `/app/runtime/output/connection_state.jsonl` — per-connection state records
- `/app/runtime/output/recovery_report.json` — pool accounting and processing metadata

## Processing Phases

1. **Sequencer**: Loads events from all gateway sources, normalizes timestamps using per-source epoch offsets from config, produces globally-ordered event stream
2. **Event Processor**: Validates per-source sequence monotonicity, deduplicates, splits into batches
3. **Handlers**: Dispatches events through the state machine with pool slot management
4. **Reconciler**: Merges batch results, sweeps stale reservations, deduplicates cross-source events, normalizes connection IDs
5. **Export**: Produces final state snapshot and recovery report

## TCP State Model

Extended RFC-793 model with half-close tracking:

**CLOSED** → **LISTEN** → **SYN_RCVD** → **ESTABLISHED**

From ESTABLISHED, two close paths:
- **Active close** (local initiates): ESTABLISHED → HALF_CLOSED_LOCAL → TIME_WAIT → CLOSED
- **Passive close** (remote initiates): ESTABLISHED → HALF_CLOSED_REMOTE → TIME_WAIT → CLOSED

**TIME_WAIT** duration is configured by `time_wait_duration_seconds` (30s).

## Connection Pool

Two-phase slot management:
- **Reserve**: Slot reserved on SYN_RECV (handshake initiated)
- **Confirm**: Slot confirmed on ESTABLISHED (handshake complete)
- **Release**: Slot released on CLOSED (connection terminated)

Stale reservations (not confirmed within timeout) should be swept. The timeout should accommodate the full SYN retransmission cycle documented in the protocol specification comments (SYN_RETRY_INTERVAL × MAX_RETRIES).

## Event Direction Semantics

Events have an implicit direction:
- **Local events**: PASSIVE_OPEN, ACTIVE_OPEN, CLOSE, TIMEOUT (initiated by us)
- **Remote events**: SYN_RECV, SYN_ACK_RECV, ACK_RECV, FIN_RECV (received from peer)

The state machine requires the correct direction to select the proper transition.

## Configuration

- `max_connections = 12`
- `time_wait_duration_seconds = 30`
- `max_transitions_per_connection = 10`
- `reservation_timeout_seconds = 5`
- `batch_size = 25`
- `epoch_offset_gateway_*` — per-source timestamp correction values
- `reconciliation_window_ms = 50`
- `checkpoint_interval = 25`

## Output Schema: connection_state.jsonl

Each line is a JSON object:
- `conn_id` (string) — connection identifier (format: `conn_NNN`)
- `source_addr` (string) — source IP:port
- `dest_addr` (string) — destination IP:port
- `state` (string) — final TCP state
- `created_at` (string) — ISO-8601 timestamp
- `last_transition_at` (string) — ISO-8601 timestamp
- `transitions_count` (integer) — total state transitions
- `transition_history` (array) — transition records with from/to/event/timestamp

## Output Schema: recovery_report.json

- `sha256` (string) — SHA-256 over state file lines
- `record_count` (integer)
- `state_distribution` (object) — count per state
- `pool` (object) — max_connections, active_count, reserved_count, confirmed_count, total_allocated, released, evictions
- `pool_slot_history` (array) — chronological reserve/confirm/release events
- `eviction_log` (array)
- `handler_stats`, `event_stats`, `reconciler_stats` (objects)
- `exported_at` (string)
