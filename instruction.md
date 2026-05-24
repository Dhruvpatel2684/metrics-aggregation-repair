# Connection State Recovery — Operational Context

## Situation

A TCP connection state recovery runtime replays event logs from multiple network gateways through a state machine to reconstruct connection lifecycle states. The system processes events through a connection pool, tracks state transitions, and produces a snapshot of final connection states with pool accounting metadata.

After a routine deployment, the recovery output exhibits several anomalies that violate expected TCP connection lifecycle invariants.

## Observed Symptoms

Running `python3 /app/runtime/run_recovery.py` produces output that does not match expected connection lifecycle behavior. The recovery snapshot shows:

- Connections that should have completed their full lifecycle appear stuck in intermediate states
- The connection pool reports accounting inconsistencies between allocated and released slots
- Some healthy connections are unexpectedly terminated despite having normal traffic patterns
- The transition history for certain connections contains entries that should not occur in a well-behaved TCP state machine
- Pool slot release events appear to happen prematurely relative to connection finalization

## Expected Behavior

After repair, the recovery output must satisfy standard TCP connection lifecycle invariants across all processed connections and maintain correct pool slot accounting throughout the entire event processing sequence.

## Environment

The runtime environment already contains the required system-wide Python tooling and pytest installation.

## Key Files

- `/app/runtime/run_recovery.py` — orchestration entrypoint
- `/app/runtime/state_machine.py` — TCP state transition logic
- `/app/runtime/connection_pool.py` — pool slot allocation and release management
- `/app/runtime/event_processor.py` — event log loading, sequencing, and deduplication
- `/app/runtime/handlers.py` — event dispatch and connection lifecycle handlers
- `/app/runtime/export.py` — snapshot and report export
- `/app/runtime/config/connections.ini` — pool size, timeouts, transition limits
- `/app/runtime/events/` — JSONL event logs from gateway sources
- `/app/runtime/output/connection_state.jsonl` — per-connection state records
- `/app/runtime/output/recovery_report.json` — pool accounting and processing metadata

## TCP State Model

The system implements a simplified RFC-793 state machine with the following states:

**CLOSED** — No connection exists. Initial and terminal state.

**LISTEN** — Waiting for incoming connection request (passive open).

**SYN_SENT** — Active open initiated, waiting for SYN-ACK.

**SYN_RCVD** — SYN received, SYN-ACK sent, waiting for ACK.

**ESTABLISHED** — Connection is open and data transfer is possible. Duplicate acknowledgments in this state should not alter connection state.

**FIN_WAIT_1** — Close initiated, waiting for ACK of FIN.

**FIN_WAIT_2** — FIN acknowledged, waiting for remote FIN.

**TIME_WAIT** — Waiting for enough time to pass to ensure remote received ACK of FIN. Duration is configured by `time_wait_duration_seconds`.

## Connection Pool Invariants

- `active_count` must never exceed `max_connections`
- `active_count` must never become negative
- Each connection occupies exactly one pool slot
- A pool slot is released exactly once, only when the connection reaches its terminal state
- Forced eviction should only occur for genuinely unhealthy connections

## Configuration

- `max_connections = 10` — maximum concurrent pool slots
- `connection_timeout_seconds = 120` — idle connection timeout
- `time_wait_duration_seconds = 30` — minimum TIME_WAIT residence before closing
- `max_transitions_per_connection = 8` — eviction threshold for transition count

## Event Processing

Events arrive from multiple gateway sources, each with independent sequence numbering. The processor must:

- Validate that each event's sequence number represents a new event (not a reprocessing of an already-seen sequence)
- Handle events in timestamp order across all sources
- Ensure that event handlers interact correctly with both the state machine and pool manager

## Output Schema: connection_state.jsonl

Each line is a JSON object representing one connection's final state:

- `conn_id` (string) — unique connection identifier
- `source_addr` (string) — source IP:port
- `dest_addr` (string) — destination IP:port
- `state` (string) — final TCP state (one of the valid states above)
- `created_at` (string) — ISO-8601 UTC timestamp of connection creation
- `last_transition_at` (string) — ISO-8601 UTC timestamp of most recent transition
- `transitions_count` (integer) — total number of state transitions recorded
- `transition_history` (array) — list of transition records, each containing:
  - `from` (string) — source state
  - `to` (string) — destination state
  - `event` (string) — triggering event type
  - `timestamp` (string) — ISO-8601 UTC timestamp

## Output Schema: recovery_report.json

- `sha256` (string) — SHA-256 digest over concatenated JSONL state lines
- `record_count` (integer) — total connection records
- `state_distribution` (object) — count of connections per final state
- `pool` (object) — pool accounting summary:
  - `max_connections` (integer)
  - `active_count` (integer) — currently active slots
  - `total_allocated` (integer) — total slots ever allocated
  - `released` (integer) — total slots released
  - `evictions` (integer) — forced eviction count
- `pool_slot_history` (array) — chronological allocation/release events:
  - `action` (string) — "allocate" or "release"
  - `conn_id` (string)
  - `timestamp` (string) — for allocations
  - `state_at_release` (string) — for releases
  - `reason` (string) — for releases
  - `active_after` (integer) — active_count after this action
- `eviction_log` (array) — forced eviction records
- `handler_stats` (object) — event handling statistics
- `event_stats` (object) — event processing statistics
- `exported_at` (string) — UTC timestamp of export
