#!/bin/bash

mkdir -p /logs/verifier

# Run the spatial indexer to generate output
cd /app
python3 -m runtime.run_indexer

# Run tests against the generated output
uv run --with pytest pytest /tests/test_spatial.py -v 2>&1 | tee /logs/verifier/test_output.txt
TEST_RESULT=${PIPESTATUS[0]}

if [ $TEST_RESULT -eq 0 ]; then
    echo "1" > /logs/verifier/reward.txt
else
    echo "0" > /logs/verifier/reward.txt
fi
