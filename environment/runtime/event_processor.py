"""
Event processor: orchestrates batch processing of sequenced events
through the handler and pool manager.
"""

import configparser
from datetime import timedelta

from .handlers import EventHandler
from .connection_pool import ConnectionPool


class BatchProcessor:
    """Processes events in batches, managing pool reservations and state transitions."""

    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.batch_size = self.config.getint("processing", "batch_size")
        self.handler = EventHandler(config_path)

        max_conn = self.config.getint("pool", "max_connections")
        timeout = self.config.getint("pool", "reservation_timeout_seconds")
        self.pool = ConnectionPool(max_conn, timeout)

        self.time_wait_duration = self.config.getfloat(
            "timeouts", "time_wait_duration_seconds"
        )
        self.batch_snapshots = []

    def process_events(self, events):
        """Process all events in batches."""
        batches = self._split_batches(events)
        for batch_idx, batch in enumerate(batches):
            self._process_batch(batch, batch_idx)
        return self.handler.get_all_connections()

    def _split_batches(self, events):
        """Split events into fixed-size batches."""
        batches = []
        for i in range(0, len(events), self.batch_size):
            batches.append(events[i:i + self.batch_size])
        return batches

    def _process_batch(self, batch, batch_idx):
        """Process a single batch of events."""
        for event in batch:
            self._process_single_event(event)

        current_time = batch[-1]["_timestamp"] if batch else None
        if current_time and batch_idx % self.config.getint("pool", "sweep_interval_batches") == 0:
            self.pool.sweep_stale(current_time)

        self._take_snapshot(batch_idx)

    def _process_single_event(self, event):
        """Process one event: handle state transition and pool operations."""
        conn_id = event["conn_id"]
        event_type = event["event_type"]
        timestamp = event["_timestamp"]

        self.pool.update_activity(conn_id, timestamp)

        if event_type in ("ACTIVE_OPEN", "PASSIVE_OPEN"):
            self.pool.reserve(conn_id, timestamp)

        success, conn = self.handler.handle_event(event)

        if success and conn.state == "ESTABLISHED":
            self.pool.confirm(conn_id, timestamp)

        if success and conn.state == "CLOSED":
            self.pool.release(conn_id)

        if event_type == "TIMEOUT" and conn.state == "TIME_WAIT":
            elapsed = (timestamp - conn.entered_current_at).total_seconds()
            if elapsed >= self.time_wait_duration:
                conn.state = "CLOSED"
                conn.entered_current_at = timestamp
                conn.transitions_count += 1
                conn.transition_history.append({
                    "from": "TIME_WAIT",
                    "to": "CLOSED",
                    "event": "TIMEOUT",
                    "direction": "local",
                    "timestamp": timestamp.isoformat(),
                })
                self.pool.release(conn_id)

    def _take_snapshot(self, batch_idx):
        """Take a snapshot of connection states after this batch."""
        snapshot = {}
        for conn_id, conn in self.handler.get_all_connections().items():
            snapshot[conn_id] = {
                "state": conn.state,
                "transitions_count": conn.transitions_count,
                "batch_idx": batch_idx,
            }
        self.batch_snapshots.append(snapshot)

    def get_batch_snapshots(self):
        return self.batch_snapshots
