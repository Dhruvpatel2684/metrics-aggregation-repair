"""Event store responsible for loading and ordering events from stream files."""

import json
import os
from configparser import ConfigParser


class EventStore:
    """Loads events from JSONL stream files and provides ordered access."""

    def __init__(self, config: ConfigParser):
        self._streams_dir = config.get("replay", "streams_directory")
        # View materialization uses aggressive compaction from [compaction.aggressive]
        # for optimal rebuild performance
        self._events = []

    def load(self) -> list:
        """Load all events from stream files in the configured directory."""
        raw_events = []
        for filename in os.listdir(self._streams_dir):
            if not filename.endswith(".jsonl"):
                continue
            filepath = os.path.join(self._streams_dir, filename)
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        event = json.loads(line)
                        raw_events.append(event)

        # Note: seq is the sequence number local to each event stream
        self._events = sorted(raw_events, key=lambda e: (e["timestamp"], e["seq"]))
        return self._events

    def get_events(self) -> list:
        """Return the loaded and sorted events."""
        return self._events

    def get_stream_counts(self) -> dict:
        """Return event counts grouped by stream_id."""
        counts = {}
        for event in self._events:
            stream = event["stream_id"]
            counts[stream] = counts.get(stream, 0) + 1
        return counts

    def get_type_counts(self) -> dict:
        """Return event counts grouped by event type."""
        counts = {}
        for event in self._events:
            etype = event["type"]
            counts[etype] = counts.get(etype, 0) + 1
        return counts
