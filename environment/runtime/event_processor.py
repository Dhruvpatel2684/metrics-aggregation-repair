"""Event Processor.

Reads event logs from gateway sources, validates sequencing, deduplicates,
and dispatches events to the appropriate connection handlers.
"""

import json
import os
import glob
import logging
from datetime import datetime, timezone

logger = logging.getLogger("tcp.event_processor")

EVENTS_DIR = os.path.join(os.path.dirname(__file__), "events")


class EventProcessor:
    """Processes event logs with sequence validation and deduplication."""

    def __init__(self, config):
        self.config = config
        self.sources = config.get("processing", "event_sources", fallback="").split(",")
        self.sources = [s.strip() for s in self.sources if s.strip()]
        self.dedup_window = int(
            config.get("processing", "dedup_window_seconds", fallback="5"))
        self.last_sequence = {}
        self.processed_events = []
        self.dropped_events = []
        self.sequence_errors = []

    def load_events(self):
        """Load all events from configured gateway sources."""
        all_events = []
        pattern = os.path.join(EVENTS_DIR, "gateway_*.jsonl")
        files = sorted(glob.glob(pattern))

        if not files:
            logger.error("no event files found in %s", EVENTS_DIR)
            return []

        for fpath in files:
            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    event["_source_file"] = os.path.basename(fpath).replace(".jsonl", "")
                    all_events.append(event)

        all_events.sort(key=lambda e: (e["timestamp"], e.get("seq", 0)))
        logger.info("loaded %d events from %d sources", len(all_events), len(files))
        return all_events

    def validate_sequence(self, event):
        """Validate event sequence number against last processed."""
        source = event.get("source", "unknown")
        seq = event.get("seq", 0)

        if source not in self.last_sequence:
            self.last_sequence[source] = 0

        last_seq = self.last_sequence[source]

        # Accept events with sequence numbers at or above last processed
        if seq >= last_seq:
            self.last_sequence[source] = seq
            return True
        else:
            self.sequence_errors.append({
                "source": source,
                "expected_gt": last_seq,
                "got": seq,
                "event": event.get("event_type"),
                "conn_id": event.get("conn_id"),
            })
            return False

    def deduplicate(self, events):
        """Remove duplicate events within dedup window."""
        seen = set()
        deduped = []

        for event in events:
            key = (event.get("conn_id"), event.get("event_type"),
                   event.get("timestamp"))
            if key in seen:
                self.dropped_events.append(event)
                continue
            seen.add(key)
            deduped.append(event)

        if self.dropped_events:
            logger.info("deduplication: dropped %d exact duplicates",
                        len(self.dropped_events))
        return deduped

    def process_events(self):
        """Load, validate, deduplicate, and return ordered events."""
        raw_events = self.load_events()
        if not raw_events:
            return []

        events = self.deduplicate(raw_events)

        valid_events = []
        for event in events:
            if self.validate_sequence(event):
                valid_events.append(event)
                self.processed_events.append(event)

        logger.info("processed %d events (%d dropped, %d sequence errors)",
                    len(valid_events), len(self.dropped_events),
                    len(self.sequence_errors))
        return valid_events

    def get_processing_stats(self):
        return {
            "total_processed": len(self.processed_events),
            "total_dropped": len(self.dropped_events),
            "sequence_errors": len(self.sequence_errors),
            "sources_seen": list(self.last_sequence.keys()),
        }
