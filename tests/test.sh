#!/bin/bash
set -euo pipefail

mkdir -p /logs/verifier

# Tests run the runtime directly via setup_module — no pre-run needed
# pytest is installed system-wide via the Dockerfile
set +e
uv run --with pytest pytest -v /tests/test_connections.py
TEST_EXIT=$?
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt

exit "$TEST_EXIT"
