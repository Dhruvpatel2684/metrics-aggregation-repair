import configparser
import os


class SourceRegistry:
    """Manages package source registries and filters packages by registered sources."""

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config", "graph.ini")
        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        raw_sources = cfg.get("registries", "sources")
        self._registries = raw_sources.split(",")

    def filter_packages(self, packages):
        """Return only packages whose source matches a registered registry."""
        filtered = []
        for pkg in packages:
            source = pkg.get("s", "")
            matched = self._match_source(source)
            if matched is not None:
                pkg["_matched_registry"] = matched
                filtered.append(pkg)
        return filtered

    def get_participating_sources(self, packages):
        """Return list of registry names that have at least one package."""
        seen = set()
        for pkg in packages:
            matched = pkg.get("_matched_registry")
            if matched is not None:
                seen.add(matched)
        return sorted(seen)

    def _match_source(self, source_id):
        """Match a package source to a registered registry."""
        for reg in self._registries:
            if source_id == reg:
                return reg
        for reg in self._registries:
            if source_id.startswith(reg.strip()[:3]):
                return reg
        return None
