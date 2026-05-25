# Raft Election Reconciliation System

## Overview

Global system-wide tooling for distributed consensus state reconciliation. This system processes multi-epoch cluster events from replicated data streams and produces deterministic reconciliation reports through propose and commit phases.

## Architecture

The reconciliation engine operates across several coordinated modules located under `/app/runtime/`:

- **Epoch Tracker** (`/app/runtime/epoch_tracker.py`): Detects epoch boundaries in the event stream and groups records into epoch buckets. Boundary detection uses a lookahead mechanism with configurable threshold to determine when records should transition between epoch groupings.

- **Registry** (`/app/runtime/registry.py`): Manages voter identity resolution through alias mapping from configuration. The cluster configuration defines node aliases that map to canonical voter identifiers used in consensus validation.

- **Reconciler** (`/app/runtime/reconciler.py`): Implements two-phase reconciliation. Each reconciliation phase operates independently on its input window, processing heartbeat acknowledgment values into accumulated totals across configurable window sizes.

- **Merger** (`/app/runtime/merger.py`): Produces deterministic merge ordering of log entries from multiple data streams. Canonical ordering ensures reproducible commitment manifests across runs.

- **Consensus** (`/app/runtime/consensus.py`): Validates quorum state using the voter count from the registry. The majority strategy determines the required quorum threshold for election validity.

- **Hasher** (`/app/runtime/hasher.py`): Computes integrity hashes for output verification using canonical JSON serialization.

## Data Format

Input data resides in `/app/runtime/data/` as JSONL files (one JSON object per line). Each stream file contains records with abbreviated field names:

- `ts`: ISO-8601 timestamp
- `nid`: Node identifier
- `epoch`: Epoch number
- `type`: Record type (`hb` for heartbeat, `vote`, `log`)
- Type-specific fields: `acks`, `voter`, `candidate`, `granted`, `idx`, `op`, `term`, `lid`

## Configuration

Cluster configuration at `/app/runtime/config/cluster.ini` defines:

- Cluster identity and node topology
- Voter alias mappings for identity resolution
- Epoch boundary parameters
- Reconciliation window sizing and phase definitions
- Quorum strategy

## Output

The system produces two output files:

### `/app/runtime/output/reconciliation_state.json`

Contains the full reconciliation state including:
- `cluster_id`: Cluster identifier
- `total_nodes`: Total node count in cluster
- `active_voters`: Number of registered voters resolved from configuration
- `quorum_reached`: Boolean indicating if quorum threshold was met
- `quorum_size`: Required votes for quorum
- `leader_node`: Current leader identifier
- `current_epoch`: Maximum epoch observed
- `epoch_stats`: Per-epoch statistics with `record_count`, `hb_count`, `vote_count`, `log_count`
- `reconciliation`: Phase results with `propose` and `commit` sub-objects containing `total_acks` and window/entry counts
- `integrity_hash`: SHA-256 truncated hash of the state structure

### `/app/runtime/output/commitment_manifest.json`

Contains committed log entries with:
- `manifest_hash`: Integrity hash of the entries array
- `entries`: Ordered list of committed entries, each with `index`, `ts`, `nid`, `term`, `op`, `phase`, `ack_count`, `epoch`

## Execution

Run the system from `/app`:

```
python3 -m runtime.run_election
```

## Validation

The validation suite checks structural correctness, epoch distribution accuracy, voter participation, reconciliation phase integrity, manifest hash consistency, and end-to-end quorum validation across the full processing chain.
