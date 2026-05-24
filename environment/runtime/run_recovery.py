#!/usr/bin/env python3
"""TCP Connection State Recovery - Orchestrator."""

import sys
import os
import logging
import configparser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.state_machine import StateMachine
from runtime.connection_pool import ConnectionPool
from runtime.event_processor import EventProcessor
from runtime.handlers import ConnectionHandlers
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

    state_machine = StateMachine(config)
    pool = ConnectionPool(config)
    event_processor = EventProcessor(config)
    handlers = ConnectionHandlers(state_machine, pool)

    events = event_processor.process_events()
    if not events:
        logger.error("no events to process, aborting")
        sys.exit(1)

    logger.info("dispatching %d events to handlers", len(events))

    for event in events:
        handlers.handle_event(event)

    # Check for TIME_WAIT expiry on remaining connections
    if events:
        latest_ts = events[-1]["timestamp"]
        for conn_id, conn in handlers.get_all_connections().items():
            if state_machine.check_time_wait_expiry(conn, latest_ts):
                state_machine.transition(conn, "TIMEOUT", latest_ts)
                pool.release_slot(conn_id, "CLOSED", reason="final_sweep")

    connections = handlers.get_all_connections()
    handler_stats = handlers.get_handler_stats()
    event_stats = event_processor.get_processing_stats()

    state_path, report_path = export_connection_state(
        connections, pool, handler_stats, event_stats, OUTPUT_DIR)

    logger.info("recovery complete")
    logger.info("connection state: %s", state_path)
    logger.info("recovery report: %s", report_path)


if __name__ == "__main__":
    main()
