"""Projector filters events based on configured tracked types."""

from configparser import ConfigParser


class Projector:
    """Filters the event stream to include only relevant event types."""

    def __init__(self, config: ConfigParser):
        raw = config.get("events", "tracked_types")
        self._tracked = set(raw.split(","))

    def filter(self, events: list) -> list:
        """Return only events whose type is in the tracked set."""
        return [e for e in events if e["type"] in self._tracked]

    def get_tracked_types(self) -> set:
        """Return the set of tracked event types."""
        return self._tracked.copy()
