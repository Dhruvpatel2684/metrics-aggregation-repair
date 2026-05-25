"""Main entry point for the event replay engine.

Orchestrates the replay stages: load events from streams, filter by
tracked types, reduce into account balances, compact views, and export
results to output files.
"""

import os
import sys
from configparser import ConfigParser

from runtime.event_store import EventStore
from runtime.projector import Projector
from runtime.reducer import Reducer
from runtime.materializer import Materializer
from runtime.export import Exporter


def load_config() -> ConfigParser:
    """Load the replay configuration from the standard location."""
    config = ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config", "replay.ini")
    if not os.path.exists(config_path):
        config_path = "/app/runtime/config/replay.ini"
    config.read(config_path)
    return config


def main():
    """Execute the full event replay process."""
    config = load_config()
    output_dir = config.get("replay", "output_directory")

    # Stage 1: Load and order events from all streams
    store = EventStore(config)
    all_events = store.load()
    print(f"Loaded {len(all_events)} events from streams")

    # Stage 2: Filter events to tracked types only
    projector = Projector(config)
    filtered = projector.filter(all_events)
    print(f"Filtered to {len(filtered)} tracked events")

    # Stage 3: Reduce events into account balances
    reducer = Reducer(config)
    reducer.process(filtered)
    balances = reducer.get_balances()
    print(f"Reduced to {len(balances)} account balances")

    # Stage 4: Compact materialized views
    materializer = Materializer(config)
    compactions = materializer.compact_if_needed(reducer.get_event_counts())
    print(f"Compaction: {compactions} views compacted (threshold={materializer.get_threshold()})")

    # Stage 5: Export results
    exporter = Exporter(output_dir)
    exporter.write_account_views(
        balances=balances,
        event_counts=reducer.get_event_counts(),
        last_updated=reducer.get_last_updated(),
        total_events=len(filtered),
        snapshot_count=reducer.get_snapshot_count(),
        compaction_threshold=materializer.get_threshold(),
        compactions_performed=materializer.get_compactions_performed()
    )
    exporter.write_replay_report(
        total_events_loaded=len(all_events),
        type_counts=store.get_type_counts(),
        stream_counts=store.get_stream_counts(),
        batch_count=reducer.get_batch_count(),
        balances=balances,
        compaction_threshold=materializer.get_threshold(),
        compactions_performed=materializer.get_compactions_performed()
    )
    print(f"Export complete: {output_dir}")


if __name__ == "__main__":
    main()
