#!/usr/bin/env python3
"""TCP Connection State Recovery — Orchestrator.

Multi-phase pipeline:
1. Sequencer: normalize timestamps, merge-sort events
2. Event Processor: validate sequences, deduplicate, batch
3. Handlers: dispatch events through state machine + pool
4. Reconciler: merge batch results, sweep stale, deduplicate cross-source
5. Export: produce final state snapshot + report
"""

import sys
import os
import logging
import configparser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.sequencer import EventSequencer
from runtime.event_processor import EventProcessor
from runtime.state_machine import StateMachine
from runtime.connection_pool import ConnectionPool
from runtime.handlers import ConnectionHandlers
from runtime.reconciler import Reconciler
from runtime.export import export_connection_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("tcp.orchestrator")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "connections.ini")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def main():
    logger.info("TCP connection state recovery starting")
    config = load_config()

    # Phase 1: Sequence events
    sequencer = EventSequencer(config)
    sequenced_events = sequencer.load_and_sequence()
    if not sequenced_events:
        logger.error("no events to process")
        sys.exit(1)

    # Phase 2: Process events (validate, deduplicate, batch)
    processor = EventProcessor(config)
    batches = processor.process_events(sequenced_events)
    if not batches:
        logger.error("no valid events after processing")
        sys.exit(1)

    # Phase 3: Handle events through state machine
    state_machine = StateMachine(config)
    pool = ConnectionPool(config)
    handlers = ConnectionHandlers(state_machine, pool)
    reconciler = Reconciler(config, pool)

    for batch_idx, batch in enumerate(batches):
        logger.info("processing batch %d (%d events)", batch_idx + 1, len(batch))
        for event in batch:
            handlers.handle_event(event)

        # Snapshot batch results for reconciliation
        reconciler.add_batch_result(handlers.get_all_connections())

    # Phase 4: Reconcile
    connections = handlers.get_all_connections()
    latest_ts = sequenced_events[-1]["timestamp"] if sequenced_events else None

    if latest_ts:
        # Final TIME_WAIT sweep
        for conn_id, conn in list(connections.items()):
            if state_machine.check_time_wait_expiry(conn, latest_ts):
                state_machine.transition(conn, "TIMEOUT", latest_ts, direction="local")
                pool.release_slot(conn_id, "CLOSED", reason="final_sweep")

    connections = reconciler.reconcile(connections, latest_ts or "2024-03-15T10:05:00.000Z")

    # Phase 5: Export
    handler_stats = handlers.get_handler_stats()
    event_stats = processor.get_processing_stats()
    reconciler_stats = reconciler.get_reconciler_stats()

    state_path, report_path = export_connection_state(
        connections, pool, handler_stats, event_stats, reconciler_stats, OUTPUT_DIR)

    logger.info("recovery complete: %s", state_path)


if __name__ == "__main__":
    main()
