"""Materializer handles view compaction based on event thresholds."""

from configparser import ConfigParser


class Materializer:
    """Manages materialized view compaction during replay."""

    def __init__(self, config: ConfigParser):
        self._threshold = config.getint("compaction", "threshold_events")
        self._compactions = 0

    def compact_if_needed(self, event_counts: dict) -> int:
        """Perform compaction for accounts exceeding the threshold.

        Returns the number of compactions performed in this pass.
        """
        compacted = 0
        for acct, count in event_counts.items():
            if count >= self._threshold:
                compacted += 1
        self._compactions = compacted
        return compacted

    def get_threshold(self) -> int:
        """Return the compaction threshold."""
        return self._threshold

    def get_compactions_performed(self) -> int:
        """Return total compactions performed."""
        return self._compactions
