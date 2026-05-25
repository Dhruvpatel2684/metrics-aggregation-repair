# Log Replay Repair — Debugging Task

## Overview

An event sourcing system replays event logs from multiple streams to rebuild materialized views representing account balances. The replay engine loads events from stream files, filters them by type, processes them in batches to compute balances, performs view compaction, and exports the results. The system currently produces incorrect output due to defects in the processing stages.

Your objective is to identify and fix the defects so that the replay engine produces correct materialized views matching the expected account balances.

## Environment

This task uses global system-wide tooling with Python 3.11 runtime. All source code, configuration, and data files are located under `/app/runtime/`. The replay engine uses only Python standard library modules.

## Architecture

The replay engine processes events through five sequential stages:

1. **Event Store** — Loads events from all `.jsonl` stream files and sorts them into a single ordered sequence
2. **Projector** — Filters the event sequence to include only configured tracked types
3. **Reducer** — Processes filtered events in fixed-size batches to compute account balances
4. **Materializer** — Compacts materialized views when per-account event counts exceed the configured threshold
5. **Exporter** — Writes final account state and replay metadata to output files

## Key Files

| File | Absolute Path | Purpose |
|------|---------------|---------|
| Configuration | `/app/runtime/config/replay.ini` | Replay settings, event types, compaction thresholds |
| Event Store | `/app/runtime/event_store.py` | Loads and orders events from stream files |
| Projector | `/app/runtime/projector.py` | Filters events by tracked types |
| Reducer | `/app/runtime/reducer.py` | Batch processing and balance computation |
| Materializer | `/app/runtime/materializer.py` | View compaction based on event thresholds |
| Exporter | `/app/runtime/export.py` | Output file generation |
| Entry Point | `/app/runtime/run_replay.py` | Orchestrates the replay stages |

## Data Streams

Three event stream files are located in `/app/runtime/streams/`:

- `accounts.jsonl` — Account lifecycle events (created, balance updates, snapshots)
- `transfers.jsonl` — Inter-account transfer completions
- `system.jsonl` — System checkpoints and operational markers

Each event has the structure:
```json
{
  "stream_id": "string",
  "seq": "integer",
  "timestamp": "ISO-8601 string",
  "type": "string",
  "data": {}
}
```

## Event Types

- `account_created` — Initializes an account with zero balance
- `balance_updated` — Credits or debits an account by a specified amount
- `transfer_completed` — Moves funds between two accounts
- `snapshot_taken` — Authoritatively resets an account balance to the snapshot value
- `system_checkpoint` — System-level checkpoint marker (not tracked for balance computation)

**Important:** `snapshot_taken` events authoritatively reset account balances. When a snapshot is encountered, the account balance must be set to exactly the value specified in the snapshot, discarding any previously computed balance.

## Event Ordering

When events from different streams share a timestamp, ordering must be deterministic by stream origin then sequence number. The `seq` field is the sequence number local to each event stream and does not provide global ordering across streams.

## Configuration

The replay configuration at `/app/runtime/config/replay.ini` defines:

- **Batch size** — Number of events processed per reduction batch
- **Tracked types** — Comma-separated list of event types to include in processing
- **Compaction thresholds** — Event count thresholds triggering view compaction
- **Ordering strategy** — Fields used for event sort ordering

## Output Specification

### `/app/runtime/output/account_views.json`

```json
{
  "accounts": {
    "<account_id>": {
      "balance": "integer — final computed balance",
      "event_count": "integer — number of events processed for this account",
      "last_updated": "string — ISO-8601 timestamp of last event"
    }
  },
  "metadata": {
    "total_events_processed": "integer — total events after filtering",
    "snapshot_events_applied": "integer — number of snapshot events processed",
    "compaction_threshold": "integer — configured compaction threshold",
    "compactions_performed": "integer — number of accounts that were compacted"
  }
}
```

### `/app/runtime/output/replay_report.json`

```json
{
  "total_events_loaded": "integer — total events from all streams before filtering",
  "events_by_type": "object — count per event type from raw loaded events",
  "events_by_stream": "object — count per stream_id from raw loaded events",
  "batch_count": "integer — number of batches processed",
  "final_balances": "object — account_id to final balance mapping",
  "compaction_applied": "boolean — whether any compaction occurred",
  "compaction_threshold": "integer — configured threshold value",
  "integrity_hash": "string — SHA-256 hex digest for output verification"
}
```

## Expected Results

When all defects are fixed, the system produces these account balances:

- `acct_001`: 1500
- `acct_002`: 2300
- `acct_003`: 800
- `acct_004`: 3100
- `acct_005`: 1900

## Running the System

```bash
cd /app
python3 -m runtime.run_replay
```

Output files are written to `/app/runtime/output/`.

## Validation

Tests verify:
- Output file existence and structure
- Correct account balances
- Proper snapshot event handling
- Compaction configuration accuracy
- Output integrity via hash verification
