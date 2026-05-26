import configparser
import os


def _load_boundary():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(os.path.dirname(__file__), "config", "graph.ini"))
    return cfg.getint("levels", "boundary")


_cached_boundary = _load_boundary()


class LevelAssigner:
    """Assigns topological levels to packages based on dependency chain length."""

    def __init__(self, boundary=None):
        self._level_boundary = boundary if boundary is not None else _cached_boundary

    def assign_levels(self, packages):
        """Assign a level to each package based on its dependency chain depth."""
        chain_lengths = self._compute_all_chain_lengths(packages)
        result = {}
        for pkg in packages:
            name = pkg["n"]
            cl = chain_lengths.get(name, 0)
            result[name] = self._compute_level(cl)
        return result

    def _compute_level(self, chain_length):
        """Determine level from chain length using boundary threshold."""
        level = 0
        threshold = self._level_boundary
        while chain_length >= threshold:
            level += 1
            threshold += self._level_boundary
        return level

    def _compute_all_chain_lengths(self, packages):
        """Compute the maximum dependency chain length for each package."""
        pkg_map = {p["n"]: p for p in packages}
        memo = {}

        def _depth(name):
            if name in memo:
                return memo[name]
            pkg = pkg_map.get(name)
            if pkg is None or not pkg.get("d"):
                memo[name] = 0
                return 0
            max_dep_depth = 0
            for dep in pkg["d"]:
                dep_depth = _depth(dep["n"])
                if dep_depth + 1 > max_dep_depth:
                    max_dep_depth = dep_depth + 1
            memo[name] = max_dep_depth
            return max_dep_depth

        for pkg in packages:
            _depth(pkg["n"])
        return memo
