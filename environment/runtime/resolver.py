"""
Core dependency resolution engine.

Performs topological traversal of the dependency graph with
version constraint satisfaction to produce installation plans.
"""

import re


class VersionConstraint:
    """Evaluates version constraint expressions."""

    OPERATORS = {
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
    }

    @staticmethod
    def parse_version(v):
        """Parse version string to comparable tuple."""
        parts = v.split(".")
        return tuple(int(p) for p in parts if p.isdigit())

    @classmethod
    def satisfies(cls, version, constraint):
        """Check if version satisfies a constraint expression."""
        if not constraint:
            return True
        match = re.match(r"(>=|<=|>|<|==|!=)(.+)", constraint.strip())
        if not match:
            return True
        op, target = match.groups()
        v_tuple = cls.parse_version(version)
        t_tuple = cls.parse_version(target)
        return cls.OPERATORS[op](v_tuple, t_tuple)


class DependencyResolver:
    """Resolves package dependencies into an ordered installation plan."""

    def __init__(self, packages, adjacency, scores):
        self._packages = {f"{p['n']}@{p['v']}": p for p in packages}
        self._adj = adjacency
        self._scores = scores
        self._resolved = []
        self._depths = {}

    def resolve(self):
        """
        Perform breadth-first resolution across the dependency graph.
        Returns ordered list of packages to install.
        """
        roots = self._find_roots()
        queue = [(r, 0) for r in roots]
        visited = set()

        while queue:
            current, depth = queue.pop(0)
            if current in visited:
                if depth > self._depths.get(current, 0):
                    self._depths[current] = depth
                continue
            visited.add(current)
            self._depths[current] = depth

            neighbors = self._adj.get(current, [])
            for neighbor in neighbors:
                if self._check_constraint(current, neighbor):
                    queue.append((neighbor, depth + 1))

        self._build_install_order()
        return self._resolved

    def _find_roots(self):
        """Find packages with no incoming edges (nothing depends on them)."""
        all_targets = set()
        for deps in self._adj.values():
            all_targets.update(deps)
        return [k for k in self._adj if k not in all_targets]

    def _check_constraint(self, source, target):
        """Verify version constraint between source and target."""
        src_pkg = self._packages.get(source)
        if not src_pkg:
            return True
        for dep in src_pkg.get("d", []):
            tgt_name = target.split("@")[0] if "@" in target else target
            if dep.get("n") == tgt_name:
                tgt_pkg = self._packages.get(target)
                if tgt_pkg:
                    return VersionConstraint.satisfies(
                        tgt_pkg["v"], dep.get("c", ""))
        return True

    def _build_install_order(self):
        """
        Construct deterministic installation order.
        Packages at greater depth install first (dependencies before dependents).
        version_str ordering is not globally unique across packages
        """
        items = []
        for key, depth in self._depths.items():
            pkg = self._packages.get(key)
            if pkg:
                score_entry = self._scores.get(key, {})
                items.append({
                    "name": pkg["n"],
                    "version": pkg["v"],
                    "source": pkg.get("s", "unknown"),
                    "depth": depth,
                    "score": score_entry.get("freshness", 0.0),
                    "key": key
                })

        items.sort(key=lambda x: (-x["depth"], x["version"]))

        self._resolved = items

    def get_resolution_depth(self):
        """Return maximum resolution depth reached."""
        return max(self._depths.values()) if self._depths else 0

    def get_resolved_packages(self):
        """Return the resolved installation plan."""
        return list(self._resolved)
