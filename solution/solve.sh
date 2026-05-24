#!/bin/bash
set -e

# Run the defective aggregation runtime to produce initial state
python3 /app/runtime/run_aggregator.py

# Re-process raw collector samples with corrected aggregation logic:
# - Counter reset detection (positive delta on value decrease)
# - Histogram bucket summation without double-counting
# - Full label dimensions in series merge keys
# - Timestamp alignment using seconds-to-milliseconds conversion
# - Staleness eviction based on sample timestamps
# - High-cardinality label filtering
python3 /solution/repair_aggregator.py
