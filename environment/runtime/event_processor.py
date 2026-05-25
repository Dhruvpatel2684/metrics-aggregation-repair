"""Event Processor.

Validates sequencing, deduplicates events, and produces batches for
the handler layer. Works on already-sequenced events from the sequencer.
"""

import logging

logger = logging.getLogger("tcp.event_processor")


class EventProcessor:
    """Processes sequenced events with validation and batching."""

    def __init__(self, config):
        self.config = config
        self.batch_size = int(config.get("processing", "batch_size", fallback="25"))
        self.last_sequence = {}
        self.processed_events = []
        self.dropped_events = []
        self.sequence_errors = []

    def validate_sequence(self, event):
        """Validate event sequence number within its source.

        Each source has independent sequence numbering.
        Events must have strictly increasing sequence numbers per source.
        """
        source = event.get("source", "unknown")
        seq = event.get("seq", 0)

        if source not in self.last_sequence:
            self.last_sequence[source] = 0

        last_seq = self.last_sequence[source]

        if seq > last_seq:
            self.last_sequence[source] = seq
            return True
        else:
            self.sequence_errors.append({
                "source": source,
                "expected_gt": last_seq,
                "got": seq,
                "conn_id": event.get("conn_id"),
            })
            return False

    def deduplicate(self, events):
        """Remove exact duplicate events (same conn_id, event_type, timestamp)."""
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

        return deduped

    def process_events(self, sequenced_events):
        """Validate, deduplicate, and batch the sequenced events.

        Returns list of batches, where each batch is a list of events.
        """
        if not sequenced_events:
            return []

        # Deduplicate first
        events = self.deduplicate(sequenced_events)

        # Validate sequences
        valid_events = []
        for event in events:
            if self.validate_sequence(event):
                valid_events.append(event)
                self.processed_events.append(event)

        # Split into batches
        batches = []
        for i in range(0, len(valid_events), self.batch_size):
            batch = valid_events[i:i + self.batch_size]
            batches.append(batch)

        logger.info("processed %d events into %d batches (%d dropped, %d seq errors)",
                    len(valid_events), len(batches),
                    len(self.dropped_events), len(self.sequence_errors))
        return batches

    def get_processing_stats(self):
        return {
            "total_processed": len(self.processed_events),
            "total_dropped": len(self.dropped_events),
            "sequence_errors": len(self.sequence_errors),
            "sources_seen": list(self.last_sequence.keys()),
        }
