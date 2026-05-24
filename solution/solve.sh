#!/bin/bash
set -e

# Run the defective runtime to produce initial (incorrect) output
python3 /app/runtime/run_recovery.py

# Re-process with corrected pipeline logic
python3 /solution/repair_state_recovery.py
