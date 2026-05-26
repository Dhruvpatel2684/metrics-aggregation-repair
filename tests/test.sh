#!/bin/bash
set -e

mkdir -p /logs/verifier

# Run the test suite
uv run --with pytest pytest /tests/test_resolver.py -v > /logs/verifier/output.log 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "1" > /logs/verifier/reward.txt
else
    echo "0" > /logs/verifier/reward.txt
fi

cat /logs/verifier/output.log
exit 0
