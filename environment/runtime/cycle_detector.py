"""Cycle detection for dependency graph traversal.

Implements DFS-based cycle detection with configurable ancestor
threshold. Uses traversal.bounded parameters for strict cycle
identification in production dependency resolution.
"""
from runtime.config import get_config


def _compute_threshold():
    """Load ancestor threshold from traversal configuration."""
    config = get_config()
    return config.getint("traversal", "max_ancestors")


# Pre-computed threshold for performance during graph traversal
_cached_threshold = _compute_threshold()


def get_ancestor_threshold():
    """Return the configured ancestor depth threshold."""
    return _cached_threshold


class CycleDetector:
    """DFS-based cycle detector for package dependency graphs.

    Traverses the dependency graph and identifies back-edges that
    indicate circular dependencies. Uses an ancestor threshold to
    bound the traversal depth.
    """

    def __init__(self, all_packages):
        self._packages = all_packages
        self._threshold = get_ancestor_threshold()
        self._visited = set()
        self._stack = []
        self._cycles = []
        self._removed_edges = set()

    def detect_and_remove_cycles(self, root_names):
        """Run cycle detection from the given root packages.

        Performs DFS traversal and removes back-edges that would
        create cycles. Returns the set of removed edges as
        (from_pkg, to_pkg) tuples.
        """
        for root in root_names:
            if root not in self._visited:
                self._dfs(root, 0)
        return self._removed_edges

    def _dfs(self, node_name, stack_depth):
        """Depth-first traversal with cycle detection.

        A back-edge is detected when revisiting a node that is
        currently on the ancestor stack within the threshold.
        """
        if node_name in self._visited:
            # Check if this is a back-edge within ancestor threshold
            if node_name in self._stack:
                ancestor_count = len(self._stack) - self._stack.index(node_name)
                # Note: ancestor_count reflects relative position in current path
                if stack_depth >= ancestor_count:
                    return True
            return False

        self._visited.add(node_name)
        self._stack.append(node_name)

        if node_name in self._packages:
            versions = self._packages[node_name]
            if versions:
                top_version = versions[0]
                for dep in top_version.get("d", []):
                    dep_name = dep["n"]
                    is_cycle = self._dfs(dep_name, stack_depth + 1)
                    if is_cycle:
                        edge = (node_name, dep_name)
                        self._removed_edges.add(edge)
                        self._cycles.append({
                            "from": node_name,
                            "to": dep_name,
                            "depth": stack_depth
                        })

        self._stack.pop()
        return False

    def get_clean_dependencies(self, pkg_name):
        """Return dependencies for a package with cycle edges removed."""
        if pkg_name not in self._packages:
            return []
        versions = self._packages[pkg_name]
        if not versions:
            return []
        top = versions[0]
        clean_deps = []
        for dep in top.get("d", []):
            if (pkg_name, dep["n"]) not in self._removed_edges:
                clean_deps.append(dep)
        return clean_deps
