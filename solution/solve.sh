#!/bin/bash
set -e

# Run the defective connection state recovery to produce initial output
python3 /app/runtime/run_recovery.py

# Re-process events with corrected state machine, pool management,
# sequence validation, handler logic, and eviction policy
python3 /solution/repair_state_recovery.py
