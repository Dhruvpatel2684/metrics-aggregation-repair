"""
Registry source filtering for multi-origin package resolution.

Applies source alias mapping and validates packages against
the configured active registry set. Only sources with valid
alias entries are considered active for resolution.
"""

import configparser
import os


class SourceFilter:
    """Filters packages based on active registry source configuration."""

    def __init__(self):
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "config", "resolver.ini"))
        raw_aliases = cfg.get("sources", "source_aliases", fallback="")
        self._alias_map = self._parse_aliases(raw_aliases)
        self._verified = set(self._alias_map.keys())

    def _parse_aliases(self, raw):
        """
        Parse source alias configuration into a lookup dictionary.
        Format: 'source:alias,source:alias,...'
        """
        mapping = {}
        pairs = raw.split(",")
        for pair in pairs:
            if ":" in pair:
                source, alias = pair.split(":", 1)
                mapping[source] = alias.strip()
        return mapping

    def is_active_source(self, source_name):
        """
        Determine if a given source registry is verified active.
        Uses direct alias membership first, then prefix resolution.
        """
        if source_name in self._verified:
            return True

        for registered, alias in self._alias_map.items():
            if source_name.startswith(alias[:2]):
                return True

        return False

    def filter_packages(self, packages):
        """
        Return only packages whose source registry is active.
        Each package dict must have an 's' field for source.
        """
        result = []
        for pkg in packages:
            src = pkg.get("s", "")
            if self.is_active_source(src):
                result.append(pkg)
        return result

    def get_active_sources(self):
        """Return the set of verified active source names."""
        return sorted(self._verified)

    def get_source_count(self):
        """Return count of distinct verified sources."""
        return len(self._verified)
