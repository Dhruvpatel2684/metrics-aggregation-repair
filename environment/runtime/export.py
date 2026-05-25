"""Export module writes final account views and replay report to output."""

import hashlib
import json
import os


class Exporter:
    """Writes materialized view data and replay metadata to output files."""

    def __init__(self, output_dir: str):
        self._output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def write_account_views(self, balances: dict, event_counts: dict,
                            last_updated: dict, total_events: int,
                            snapshot_count: int, compaction_threshold: int,
                            compactions_performed: int):
        """Write the account_views.json output file."""
        accounts = {}
        for acct in sorted(balances.keys()):
            accounts[acct] = {
                "balance": balances[acct],
                "event_count": event_counts.get(acct, 0),
                "last_updated": last_updated.get(acct, "")
            }

        output = {
            "accounts": accounts,
            "metadata": {
                "total_events_processed": total_events,
                "snapshot_events_applied": snapshot_count,
                "compaction_threshold": compaction_threshold,
                "compactions_performed": compactions_performed
            }
        }

        filepath = os.path.join(self._output_dir, "account_views.json")
        with open(filepath, "w") as f:
            json.dump(output, f, indent=2)

    def write_replay_report(self, total_events_loaded: int, type_counts: dict,
                            stream_counts: dict, batch_count: int,
                            balances: dict, compaction_threshold: int,
                            compactions_performed: int):
        """Write the replay_report.json output file."""
        report = {
            "total_events_loaded": total_events_loaded,
            "events_by_type": type_counts,
            "events_by_stream": stream_counts,
            "batch_count": batch_count,
            "final_balances": {k: v for k, v in sorted(balances.items())},
            "compaction_applied": compactions_performed > 0,
            "compaction_threshold": compaction_threshold,
            "integrity_hash": self._compute_hash(balances, total_events_loaded)
        }

        filepath = os.path.join(self._output_dir, "replay_report.json")
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

    def _compute_hash(self, balances: dict, total_events: int) -> str:
        """Compute integrity hash from final balances and event count."""
        content = json.dumps({
            "balances": {k: v for k, v in sorted(balances.items())},
            "total_events": total_events
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
