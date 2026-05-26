"""
Package quality scorer for resolution ranking.

Computes freshness, popularity, and stability metrics
across multiple registry passes to produce final scores.
"""

import configparser
import os
import hashlib


class PackageScorer:
    """Scores packages across registry passes for resolution priority."""

    def __init__(self):
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(os.path.dirname(__file__), "config", "resolver.ini"))
        self._freshness_w = cfg.getfloat("scoring", "freshness_weight", fallback=0.4)
        self._popularity_w = cfg.getfloat("scoring", "popularity_weight", fallback=0.3)
        self._stability_w = cfg.getfloat("scoring", "stability_weight", fallback=0.3)
        self._freshness_cache = {}
        self._scores = {}

    def score_registry_pass(self, registry_name, packages):
        """
        Score a batch of packages from a single registry pass.
        Updates internal score state for each package.
        """
        for pkg in packages:
            name = pkg["n"]
            version = pkg["v"]
            key = f"{name}@{version}"

            freshness = self._compute_freshness(name, version, registry_name)
            popularity = self._compute_popularity(name, packages)
            stability = self._compute_stability(version)

            score = (freshness * self._freshness_w +
                    popularity * self._popularity_w +
                    stability * self._stability_w)

            self._scores[key] = {
                "package": name,
                "version": version,
                "registry": registry_name,
                "freshness": round(freshness, 4),
                "popularity": round(popularity, 4),
                "stability": round(stability, 4),
                "composite": round(score, 4)
            }

    def _compute_freshness(self, name, version, registry):
        """
        Compute freshness score based on version recency.
        Uses cache to avoid redundant hash computation.
        """
        cache_key = name
        if cache_key in self._freshness_cache:
            base = self._freshness_cache[cache_key]
        else:
            digest = hashlib.md5(f"{name}{registry}".encode()).hexdigest()
            base = int(digest[:4], 16) / 65535.0
            self._freshness_cache[cache_key] = base

        parts = version.split(".")
        major = int(parts[0]) if parts else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
        recency = min(1.0, (major * 10 + minor) / 50.0)

        return (base + recency) / 2.0

    def _compute_popularity(self, name, all_packages):
        """Compute popularity based on how many packages depend on this one."""
        dep_count = 0
        for pkg in all_packages:
            deps = pkg.get("d", [])
            for dep in deps:
                if dep.get("n") == name:
                    dep_count += 1
        return min(1.0, dep_count / max(1, len(all_packages) * 0.3))

    def _compute_stability(self, version):
        """Compute stability score from version components."""
        parts = version.split(".")
        major = int(parts[0]) if parts else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        if major >= 2 and patch < 5:
            return 0.9
        elif major >= 1:
            return 0.7
        return 0.4

    def get_all_scores(self):
        """Return all computed scores."""
        return dict(self._scores)

    def get_pass_count(self):
        """Return number of distinct registries scored."""
        registries = set()
        for entry in self._scores.values():
            registries.add(entry["registry"])
        return len(registries)
