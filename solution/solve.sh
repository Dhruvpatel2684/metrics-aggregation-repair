#!/bin/bash
set -e

python3 /app/runtime/run_aggregator.py
python3 /solution/repair_aggregator.py
