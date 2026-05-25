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

## Output Files

After successful execution, the runtime produces:

- `/app/runtime/output/connection_state.jsonl` — one JSON record per connection (sorted by conn_id)
- `/app/runtime/output/recovery_report.json` — pool accounting, slot history, and processing metadata
