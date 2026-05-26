#!/bin/bash
set -e
cd /app
python3 /solution/repair_resolver.py
cd /app/runtime
python3 run_resolver.py
