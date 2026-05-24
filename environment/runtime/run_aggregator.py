#!/usr/bin/env python3
"""Metrics aggregation runtime orchestrator."""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.ingest import load_samples
from runtime.aggregate import load_config, filter_cardinality, aggregate_samples, apply_staleness
from runtime.export import export_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("metrics.orchestrator")


def main():
    logger.info("metrics aggregation runtime starting")

    config = load_config()

    samples = load_samples()
    if not samples:
        logger.error("no samples loaded, aborting")
        sys.exit(1)

    samples = filter_cardinality(samples, config)
    aggregated = aggregate_samples(samples, config)
    aggregated = apply_staleness(aggregated, config)

    snapshot_path, integrity_path = export_snapshot(aggregated)

    logger.info("aggregation complete")
    logger.info("snapshot: %s", snapshot_path)
    logger.info("integrity: %s", integrity_path)


if __name__ == "__main__":
    main()
