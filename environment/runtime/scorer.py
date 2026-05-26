"""Resolution quality scoring.

Computes freshness and compatibility metrics for resolved packages.
Each source registry is scored independently with isolated state
to prevent cross-source score contamination.
"""


class ResolutionScorer:
    """Scores resolution quality across source registries."""

    def __init__(self, all_packages):
        self._packages = all_packages
        self._score_accumulator = {}

    def score(self, resolved, depth_map, active_sources):
        """Compute resolution score across all active sources.

        Processes each source independently and computes per-source
        contribution metrics based on freshness ratings.
        """
        source_scores = {}
        total_freshness = 0.0
        total_count = 0

        for source in sorted(active_sources):
            src_pkgs = [
                (n, info) for n, info in resolved.items()
                if info["s"] == source
            ]

            src_freshness = 0.0
            for name, info in src_pkgs:
                f = self._freshness(name, info)
                src_freshness += f
                total_freshness += f
                total_count += 1

            pkg_count = len(src_pkgs)
            avg_f = round(src_freshness / pkg_count, 4) if pkg_count else 0.0

            # Accumulate per-source contribution
            if source not in self._score_accumulator:
                self._score_accumulator[source] = {"packages": 0, "freshness": 0.0}
            self._score_accumulator[source]["packages"] += pkg_count
            self._score_accumulator[source]["freshness"] += avg_f

            source_scores[source] = {
                "packages": self._score_accumulator[source]["packages"],
                "freshness": round(self._score_accumulator[source]["freshness"], 4),
            }

        max_depth = max(depth_map.values()) if depth_map else 0

        return {
            "total_resolved": total_count,
            "max_depth_used": max_depth,
            "overall_freshness": round(total_freshness / total_count, 4) if total_count else 0.0,
            "source_scores": source_scores,
        }

    def _freshness(self, name, resolved_info):
        """Compute freshness. 1.0 = latest, -0.25 per position behind."""
        if name not in self._packages:
            return 0.0
        available = self._packages[name]
        if not available:
            return 0.0
        resolved_v = resolved_info["v"]
        for idx, entry in enumerate(available):
            if entry["v"] == resolved_v:
                return max(0.0, 1.0 - idx * 0.25)
        return 0.0
