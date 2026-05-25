"""
Event sequencer: loads events from multiple gateway sources and produces
a globally ordered event stream for processing.
"""

import glob
import json
import os
from datetime import datetime


def parse_timestamp(ts_str):
    """Parse ISO 8601 timestamp string to datetime object."""
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str)


def load_events_from_file(filepath):
    """Load all events from a single JSONL file."""
    events = []
    source_name = os.path.splitext(os.path.basename(filepath))[0]
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            event["_source"] = source_name
            event["_timestamp"] = parse_timestamp(event["timestamp"])
            events.append(event)
    return events


def load_all_events(events_dir):
    """Load events from all gateway files in the events directory."""
    all_events = []
    pattern = os.path.join(events_dir, "*.jsonl")
    files = sorted(glob.glob(pattern))
    for filepath in files:
        events = load_events_from_file(filepath)
        all_events.extend(events)
    return all_events


def sequence_events(events):
    """
    Sort events into global order by timestamp and sequence number.
    This ensures deterministic processing regardless of source.
    """
    return sorted(events, key=lambda e: (e["_timestamp"], e.get("seq", 0)))


def get_ordered_events(events_dir):
    """Main entry point: load and sequence all events."""
    events = load_all_events(events_dir)
    ordered = sequence_events(events)
    return ordered
