#!/usr/bin/env python3
"""
Main entry point for the connection state recovery pipeline.
Loads events, processes them through the state machine, reconciles results,
and exports the recovery report.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.sequencer import get_ordered_events
from runtime.event_processor import BatchProcessor
from runtime.reconciler import Reconciler
from runtime.export import export_connection_states, export_recovery_report


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "connections.ini")
    events_dir = os.path.join(base_dir, "events")
    output_dir = os.path.join(base_dir, "output")

    os.makedirs(output_dir, exist_ok=True)

    events = get_ordered_events(events_dir)
    print(f"Loaded {len(events)} events from gateway sources")

    processor = BatchProcessor(config_path)
    connections = processor.process_events(events)
    print(f"Processed {len(connections)} connections")

    reconciler = Reconciler(config_path)
    report = reconciler.reconcile(
        connections,
        processor.get_batch_snapshots(),
        processor.pool,
    )

    states_path = export_connection_states(connections, output_dir)
    report_path = export_recovery_report(report, connections, output_dir)

    print(f"Connection states written to: {states_path}")
    print(f"Recovery report written to: {report_path}")
    print(f"Anomalies detected: {len(report['anomalies'])}")

    return report


if __name__ == "__main__":
    main()
