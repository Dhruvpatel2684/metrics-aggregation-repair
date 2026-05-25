"""Repair script that patches the four defects in the event replay engine."""

import subprocess
import sys


def patch_projector():
    """Fix Bug A: Strip whitespace from tracked_types config parsing."""
    filepath = "/app/runtime/projector.py"
    with open(filepath, "r") as f:
        content = f.read()

    old = 'self._tracked = set(raw.split(","))'
    new = 'self._tracked = set(item.strip() for item in raw.split(","))'
    content = content.replace(old, new)

    with open(filepath, "w") as f:
        f.write(content)
    print("Patched projector.py: strip whitespace in tracked_types parsing")


def patch_materializer():
    """Fix Bug B: Read from correct config section for compaction threshold."""
    filepath = "/app/runtime/materializer.py"
    with open(filepath, "r") as f:
        content = f.read()

    old = 'self._threshold = config.getint("compaction", "threshold_events")'
    new = 'self._threshold = config.getint("compaction.aggressive", "threshold_events")'
    content = content.replace(old, new)

    with open(filepath, "w") as f:
        f.write(content)
    print("Patched materializer.py: use compaction.aggressive section")


def patch_reducer():
    """Fix Bug C: Change accumulation to assignment for batch fold."""
    filepath = "/app/runtime/reducer.py"
    with open(filepath, "r") as f:
        content = f.read()

    old = "self._balances[acct] += batch_balance"
    new = "self._balances[acct] = batch_balance"
    content = content.replace(old, new)

    with open(filepath, "w") as f:
        f.write(content)
    print("Patched reducer.py: change += to = for batch fold")


def patch_event_store():
    """Fix Bug D: Add stream_id to sort key for deterministic ordering."""
    filepath = "/app/runtime/event_store.py"
    with open(filepath, "r") as f:
        content = f.read()

    old = 'self._events = sorted(raw_events, key=lambda e: (e["timestamp"], e["seq"]))'
    new = 'self._events = sorted(raw_events, key=lambda e: (e["timestamp"], e["stream_id"], e["seq"]))'
    content = content.replace(old, new)

    with open(filepath, "w") as f:
        f.write(content)
    print("Patched event_store.py: add stream_id to sort key")


def main():
    """Apply all patches and re-run the replay engine."""
    print("Applying patches to event replay engine...")
    patch_projector()
    patch_materializer()
    patch_reducer()
    patch_event_store()
    print("\nAll patches applied. Re-running replay engine...")
    subprocess.run([sys.executable, "-m", "runtime.run_replay"], check=True, cwd="/app")
    print("Replay complete.")


if __name__ == "__main__":
    main()
