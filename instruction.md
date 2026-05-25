# Connection State Recovery — Debugging Task

## Situation

A TCP connection state recovery system processes event logs from network gateways to reconstruct connection lifecycle states. The system was operating correctly until `gateway_delta` was onboarded, at which point the recovery output began exhibiting multiple invariant violations.

Your task is to identify and fix the defects in the runtime so that running `python3 /app/runtime/run_recovery.py` produces output satisfying all test assertions.

## Observed Symptoms

The recovery output currently shows:

1. All connections that receive a remote FIN end up in `HALF_CLOSED_LOCAL` instead of the expected `HALF_CLOSED_REMOTE` — the half-close direction logic appears inverted for passive close scenarios
2. The connection pool leaks reserved slots — connections that complete handshake still show `reserved` status, and the `reserved_count` never reaches zero
3. Transition counts for many connections exceed the configured maximum (10) without triggering forced eviction, suggesting counts are being inflated by the batch processing layer
4. Connections from `gateway_delta` have timestamps approximately 25 minutes in the future relative to other gateways, causing the final TIME_WAIT sweep to incorrectly expire connections that should remain active
5. The pool accounting (`active_count`) does not match the actual number of non-CLOSED connections in the output

## Environment

The runtime environment has Python 3 and `uv` available as global system-wide tooling. Tests are executed via `uv run --with pytest pytest`.

## Constraints

- You must fix the existing runtime files under `/app/runtime/` — the tests import and execute these modules directly
- The solution script at `/solution/repair_state_recovery.py` should patch the runtime files and then re-run the recovery
- Do NOT replace the entire runtime — modify only the specific defective logic

## Expected Invariants

Beyond resolving the five symptoms above, the corrected output must also satisfy:

- `conn_003` has no close events in the input data and must remain in `ESTABLISHED` state
- `conn_005` has a slow handshake (~25 seconds with SYN retransmits) that falls within the protocol's maximum handshake window (`SYN_RETRY_INTERVAL × MAX_RETRIES = 3s × 10 = 30s` as documented in `state_machine.py`). It must NOT be swept as a stale reservation.
- Every connection that reaches `CLOSED` must have transitioned through `TIME_WAIT` with a `TIMEOUT` event
- Pool slot counts must never go negative at any point in the slot history
- The `sha256` field in the recovery report must match a SHA-256 recomputation over the raw lines of `connection_state.jsonl`
- Timestamps across all connections from `gateway_delta` must be within 5 minutes of other gateway timestamps after epoch normalization

## Output Files

After successful execution, the runtime produces:

- `/app/runtime/output/connection_state.jsonl` — one JSON record per connection (sorted by `conn_id`)
- `/app/runtime/output/recovery_report.json` — pool accounting, slot history, and processing metadata

## Output Schema: connection_state.jsonl

Each line is a JSON object with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `conn_id` | string | Connection identifier (format: `conn_NNN`) |
| `source_addr` | string | Source IP:port |
| `dest_addr` | string | Destination IP:port |
| `state` | string | Final TCP state (`CLOSED`, `ESTABLISHED`, `HALF_CLOSED_LOCAL`, `HALF_CLOSED_REMOTE`, `TIME_WAIT`, etc.) |
| `created_at` | string | ISO-8601 UTC timestamp of connection creation |
| `last_transition_at` | string | ISO-8601 UTC timestamp of last state transition |
| `transitions_count` | integer | Total number of state transitions recorded |
| `transition_history` | array | List of transition records |

Each entry in `transition_history` contains:

| Field | Type | Description |
|-------|------|-------------|
| `from` | string | Source state |
| `to` | string | Destination state |
| `event` | string | Triggering event type |
| `timestamp` | string | ISO-8601 UTC timestamp |

## Output Schema: recovery_report.json

| Field | Type | Description |
|-------|------|-------------|
| `sha256` | string | SHA-256 hex digest over concatenated state file lines |
| `record_count` | integer | Number of connection records |
| `state_distribution` | object | Count of connections per final state |
| `pool` | object | Pool accounting summary |
| `pool_slot_history` | array | Chronological reserve/confirm/release events |
| `eviction_log` | array | Forced eviction records |
| `handler_stats` | object | Event handling statistics |
| `event_stats` | object | Event processing statistics |
| `reconciler_stats` | object | Reconciliation statistics |
| `exported_at` | string | ISO-8601 UTC export timestamp |

The `pool` object contains:

| Field | Type | Description |
|-------|------|-------------|
| `max_connections` | integer | Configured maximum |
| `active_count` | integer | Currently active slots (reserved + confirmed) |
| `reserved_count` | integer | Slots in reserved state (should be 0 at end) |
| `confirmed_count` | integer | Slots in confirmed state |
| `total_allocated` | integer | Total slots ever allocated |
| `released` | integer | Total slots released |
| `evictions` | integer | Forced eviction count |
