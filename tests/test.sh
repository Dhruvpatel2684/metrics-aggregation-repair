#!/bin/bash
set -e
mkdir -p /logs/verifier

cd /app/runtime
python3 run_resolver.py

if uv run --with pytest pytest /tests/test_resolver.py -v; then
    echo "1" > /logs/verifier/reward.txt
else
    echo "0" > /logs/verifier/reward.txt
fi
