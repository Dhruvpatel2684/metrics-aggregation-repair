"""Event Sequencer.

Normalizes timestamps across gateway sources using per-source epoch offsets,
then produces a globally-ordered event stream via merge-sort.

Offset values in config are specified in milliseconds. The sequencer converts
them to seconds and ADDS the offset to raw timestamps to produce normalized time.
"""

import json
import os
import glob
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("tcp.sequencer")

EVENTS_DIR = os.path.join(os.path.dirname(__file__), "events")


class EventSequencer:
    """Loads, normalizes, and orders events from multiple gateway sources."""

    def __init__(self, config):
        self.config = config
        self.epoch_offsets = {}
        self._load_epoch_offsets()

    def _load_epoch_offsets(self):
        """Load per-source epoch offsets from config (in milliseconds)."""
        for key in self.config.options("sequencer"):
            if key.startswith("epoch_offset_"):
                source_name = key.replace("epoch_offset_", "")
                # Config stores offset in milliseconds
                offset_ms = float(self.config.get("sequencer", key))
                self.epoch_offsets[source_name] = offset_ms

    def normalize_timestamp(self, raw_ts, source_name):
        """Apply epoch offset to produce normalized timestamp."""
        offset_ms = self.epoch_offsets.get(source_name, 0.0)
        if offset_ms == 0.0:
            return raw_ts

        # Convert milliseconds to seconds for timedelta
        offset_seconds = offset_ms
        dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        dt = dt + timedelta(seconds=offset_seconds)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"

    def load_and_sequence(self):
        """Load all gateway event files, normalize timestamps, merge-sort."""
        all_events = []
        pattern = os.path.join(EVENTS_DIR, "gateway_*.jsonl")
        files = sorted(glob.glob(pattern))

        if not files:
            logger.error("no event files found in %s", EVENTS_DIR)
            return []

        for fpath in files:
            source_name = os.path.basename(fpath).replace(".jsonl", "")
            with open(fpath) as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event["_source_file"] = source_name
                    event["_raw_timestamp"] = event["timestamp"]

                    # Normalize timestamp using epoch offset
                    normalized = self.normalize_timestamp(
                        event["timestamp"], source_name)
                    event["timestamp"] = normalized

                    all_events.append(event)

        # Stable sort by normalized timestamp, then source, then sequence
        all_events.sort(key=lambda e: (e["timestamp"], e.get("source", ""), e.get("seq", 0)))

        logger.info("sequenced %d events from %d sources", len(all_events), len(files))
        return all_events
