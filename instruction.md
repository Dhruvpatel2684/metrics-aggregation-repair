# Raft Election Verification System

## Overview

This system implements a Raft consensus election timer and log replication verification service. It processes node heartbeat logs, election events, and log entries from a distributed cluster to produce health reports and committed entry manifests.

The runtime environment provides Global system-wide tooling including Python and pytest for verification.

## Architecture

The system reads heartbeat, election, and log replication data from multiple cluster nodes, validates election timing constraints, counts votes from registered voters, processes heartbeat acknowledgments in configurable windows, and merges results into a deterministic output.

## Key Files

- `/app/runtime/run_election.py` - Main entry point and orchestrator
- `/app/runtime/voter.py` - Voter registry and vote counting
- `/app/runtime/timer.py` - Election timeout management
- `/app/runtime/log_replicator.py` - Heartbeat window processing and log replication
- `/app/runtime/merger.py` - Deterministic event merging across nodes
- `/app/runtime/config/cluster.ini` - Cluster configuration
- `/app/runtime/data/node_alpha.json` - Node Alpha event data
- `/app/runtime/data/node_beta.json` - Node Beta event data
- `/app/runtime/data/node_gamma.json` - Node Gamma event data
- `/app/runtime/output/cluster_health.json` - Generated health report
- `/app/runtime/output/committed_entries.json` - Generated committed entries manifest

## Cluster Configuration

The cluster has 4 active voting nodes: node1, node2, node3, and node4. The election timeout should be from the strict timing configuration (150ms). Heartbeat acknowledgments are processed in windows of configurable size.

## Running

```bash
cd /app
python3 -m runtime.run_election
```

This produces two output files in `/app/runtime/output/`.

## Output Schema

### /app/runtime/output/cluster_health.json

| Field | Type | Description |
|-------|------|-------------|
| cluster_id | string | Unique cluster identifier |
| total_nodes | integer | Total number of nodes in cluster |
| active_voters | integer | Number of active voting nodes |
| quorum_reached | boolean | Whether vote quorum was achieved |
| leader_node | string | Current leader node identifier |
| election_term | integer | Current election term number |
| avg_heartbeat_ms | float | Average heartbeat interval in milliseconds |
| election_timeout_ms | integer | Configured election timeout in milliseconds |
| committed_count | integer | Number of committed log entries |

### /app/runtime/output/committed_entries.json

An array of committed log entries with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| index | integer | Log entry index |
| term | integer | Election term when entry was committed |
| node_id | string | Node that originated the entry |
| timestamp | string | ISO 8601 timestamp of the entry |
| operation | string | The operation performed |
| ack_count | integer | Acknowledgment count from heartbeat window |

## Ordering and Determinism

The correct sort order for committed entries is (timestamp, node_id, term) for deterministic ordering. This ensures that when multiple nodes produce entries at the same timestamp, the output is consistent regardless of input file ordering.

## Window-Based Processing

Heartbeat acknowledgments are processed in windows of a configured size. Each window's ack_count represents that window's aggregated value from the heartbeat records within it. Log entries use the ack_count from the most recent completed window as their replication confirmation value.

## Validation

```bash
bash /tests/test.sh
```

This runs the election verification system and validates output correctness using pytest.
