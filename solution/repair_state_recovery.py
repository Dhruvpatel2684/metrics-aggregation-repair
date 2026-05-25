#!/usr/bin/env python3
"""Repair script — patches buggy runtime files and re-runs recovery."""

import os
import sys

RUNTIME_DIR = "/app/runtime"


def patch_file(filepath, patches):
    """Apply text replacements to a file."""
    with open(filepath) as f:
        content = f.read()
    for old, new in patches:
        if old not in content:
            print(f"WARNING: patch target not found in {filepath}: {old[:60]}...")
            continue
        content = content.replace(old, new, 1)
    with open(filepath, "w") as f:
        f.write(content)


def main():
    # === FIX 1: sequencer.py — epoch offset is in ms, must divide by 1000 ===
    patch_file(os.path.join(RUNTIME_DIR, "sequencer.py"), [
        (
            "offset_seconds = offset_ms",
            "offset_seconds = offset_ms / 1000.0"
        ),
    ])

    # === FIX 2: handlers.py — _handle_transition must use correct direction ===
    # FIN_RECV and SYN_ACK_RECV are remote events, not local
    patch_file(os.path.join(RUNTIME_DIR, "handlers.py"), [
        (
            '        # Use local direction for generic transitions\n'
            '        success, new_state = self.state_machine.transition(\n'
            '            conn, event_type, timestamp, direction="local")',
            '        # Determine direction from event type\n'
            '        direction = "remote" if event_type in REMOTE_EVENTS else "local"\n'
            '        success, new_state = self.state_machine.transition(\n'
            '            conn, event_type, timestamp, direction=direction)'
        ),
    ])

    # === FIX 3: handlers.py — SYN_RECV must not create duplicate reservations ===
    patch_file(os.path.join(RUNTIME_DIR, "handlers.py"), [
        (
            '        # Reserve a pool slot — no dedup check for retransmits\n'
            '        self.pool.reserve_slot(conn_id, timestamp)',
            '        # Reserve pool slot only if not already reserved/confirmed\n'
            '        if conn_id not in self.pool.entries or self.pool.entries[conn_id].released:\n'
            '            self.pool.reserve_slot(conn_id, timestamp)'
        ),
    ])

    # === FIX 4: reconciler.py — transition count should use actual history length ===
    patch_file(os.path.join(RUNTIME_DIR, "reconciler.py"), [
        (
            '    def reconcile_transitions(self, connections):\n'
            '        """Reconcile transition counts across batches.\n'
            '\n'
            '        Accumulates transition counts from all batch snapshots to produce\n'
            '        the final count for each connection.\n'
            '        """\n'
            '        conn_total_transitions = {}\n'
            '\n'
            '        for batch_state in self.batch_results:\n'
            '            for conn_id, state_info in batch_state.items():\n'
            '                if conn_id not in conn_total_transitions:\n'
            '                    conn_total_transitions[conn_id] = 0\n'
            '                # Sum transitions across all batch appearances\n'
            '                conn_total_transitions[conn_id] += state_info["transitions_count"]\n'
            '\n'
            '        # Update connection objects with reconciled counts\n'
            '        for conn_id, total in conn_total_transitions.items():\n'
            '            if conn_id in connections:\n'
            '                connections[conn_id].transitions_count = total\n'
            '\n'
            '        return conn_total_transitions',
            '    def reconcile_transitions(self, connections):\n'
            '        """Reconcile transition counts — use actual history length after dedup."""\n'
            '        conn_total_transitions = {}\n'
            '        for conn_id, conn in connections.items():\n'
            '            conn.transitions_count = len(conn.transition_history)\n'
            '            conn_total_transitions[conn_id] = conn.transitions_count\n'
            '        return conn_total_transitions'
        ),
    ])

    # === FIX 5: reconciler.py — stale sweep must use reserved_at and correct timeout ===
    # The config timeout (5s) is too short — protocol spec says 3s * 10 retries = 30s
    patch_file(os.path.join(RUNTIME_DIR, "reconciler.py"), [
        (
            '            # Check if reservation has exceeded timeout\n'
            '            activity_dt = datetime.fromisoformat(\n'
            '                entry.last_activity_at.replace("Z", "+00:00"))\n'
            '            elapsed = (current_dt - activity_dt).total_seconds()',
            '            # Use reserved_at with protocol-derived timeout (SYN_RETRY*MAX_RETRIES=30s)\n'
            '            reserved_dt = datetime.fromisoformat(\n'
            '                entry.reserved_at.replace("Z", "+00:00"))\n'
            '            elapsed = (current_dt - reserved_dt).total_seconds()'
        ),
        (
            '            if elapsed > self.reservation_timeout:',
            '            # Protocol handshake window: SYN_RETRY_INTERVAL(3) * MAX_RETRIES(10) = 30s\n'
            '            if elapsed > 30:'
        ),
    ])

    # === FIX 7: run_recovery.py — TIME_WAIT sweep must use non-delta max timestamp ===
    # The last sequenced event may be from delta with inflated timestamp
    patch_file(os.path.join(RUNTIME_DIR, "run_recovery.py"), [
        (
            '    # Use the last sequenced event timestamp for TIME_WAIT sweep\n'
            '    latest_ts = sequenced_events[-1]["timestamp"]',
            '    # Use latest timestamp from non-delta sources to avoid inflated delta times\n'
            '    non_delta_events = [e for e in sequenced_events if e.get("source") != "gateway_delta"]\n'
            '    latest_ts = non_delta_events[-1]["timestamp"] if non_delta_events else sequenced_events[-1]["timestamp"]'
        ),
    ])

    # Re-run the recovery with patched code
    # Clear output first
    output_dir = os.path.join(RUNTIME_DIR, "output")
    for f in os.listdir(output_dir):
        if f.endswith(".jsonl") or f.endswith(".json"):
            os.remove(os.path.join(output_dir, f))

    # Re-run
    sys.path.insert(0, os.path.dirname(RUNTIME_DIR))
    # Need to reload modules since we patched the files
    import importlib
    import runtime.sequencer
    import runtime.event_processor
    import runtime.state_machine
    import runtime.connection_pool
    import runtime.handlers
    import runtime.reconciler
    import runtime.export
    import runtime.run_recovery

    importlib.reload(runtime.sequencer)
    importlib.reload(runtime.event_processor)
    importlib.reload(runtime.state_machine)
    importlib.reload(runtime.connection_pool)
    importlib.reload(runtime.handlers)
    importlib.reload(runtime.reconciler)
    importlib.reload(runtime.export)
    importlib.reload(runtime.run_recovery)

    runtime.run_recovery.main()


if __name__ == "__main__":
    main()
