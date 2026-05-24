"""Event Sequencer.

Normalizes timestamps across gateway sources using per-source epoch offsets,
then produces a globally-ordered event stream via merge-sort.

Each gateway may have a clock offset relative to the reference clock.
Offsets are specified in the config as seconds to ADD to the raw timestamp
to produce normalized time.
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
        """Load per-source epoch offsets from config (in seconds)."""
        for key in self.config.options("sequencer"):
            if key.startswith("epoch_offset_"):
                source_name = key.replace("epoch_offset_", "")
                offset_val = float(self.config.get("sequencer", key))
                self.epoch_offsets[source_name] = offset_val

    def normalize_timestamp(self, raw_ts, source_name):
        """Apply epoch offset to produce normalized timestamp.

        Args:
            raw_ts: ISO-8601 timestamp string from event
            source_name: gateway identifier for offset lookup

        Returns:
            Normalized ISO-8601 timestamp string
        """
        offset = self.epoch_offsets.get(source_name, 0.0)
        if offset == 0.0:
            return raw_ts

        dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        dt = dt + timedelta(seconds=offset)
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
                        logger.warning("skip malformed line %d in %s", line_num, fpath)
                        continue

                    event["_source_file"] = source_name
                    event["_raw_timestamp"] = event["timestamp"]

                    # Normalize timestamp using epoch offset
                    normalized = self.normalize_timestamp(
                        event["timestamp"], source_name)
                    event["timestamp"] = normalized

                    all_events.append(event)

        # Stable sort by normalized timestamp, then by sequence within source
        all_events.sort(key=lambda e: (e["timestamp"], e.get("source", ""), e.get("seq", 0)))

        logger.info("sequenced %d events from %d sources", len(all_events), len(files))
        return all_events
