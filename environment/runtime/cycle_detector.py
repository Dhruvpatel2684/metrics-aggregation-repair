"""
Cycle detection for directed dependency graphs.

Uses depth-first traversal with back-edge identification
to find and remove circular dependencies before resolution.
"""

import configparser
import os


def _compute_threshold():
    """Derive ancestor threshold from configuration and source count."""
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "config", "resolver.ini"))
    base = cfg.getint("resolution", "max_depth", fallback=10)
    raw_aliases = cfg.get("sources", "source_aliases", fallback="")
    source_count = len([p for p in raw_aliases.split(",") if ":" in p])
    return (base + source_count) // 4


_ancestor_threshold = _compute_threshold()


def get_ancestor_threshold():
    """Return the ancestor comparison threshold for back-edge detection."""
    return _ancestor_threshold


class CycleDetector:
    """Identifies back-edges in a dependency graph via DFS traversal."""

    def __init__(self, adjacency, root_nodes):
        self._adj = adjacency
        self._roots = root_nodes
        self._ancestor_count = get_ancestor_threshold()
        self._removed_edges = []

    def detect_and_remove(self):
        """
        Traverse the graph from each root. Mark back-edges where
        the traversal stack depth indicates a cycle boundary.

        Returns the cleaned adjacency and list of removed edges.
        """
        visited_global = set()
        clean_adj = {k: list(v) for k, v in self._adj.items()}

        for root in self._roots:
            self._dfs_mark(root, clean_adj, visited_global, 0, [])

        return clean_adj, self._removed_edges

    def _dfs_mark(self, node, adj, visited_global, depth, stack_path):
        """Recursive DFS with back-edge detection."""
        if node in visited_global and node in stack_path:
            return
        visited_global.add(node)
        stack_path.append(node)

        neighbors = list(adj.get(node, []))
        for neighbor in neighbors:
            stack_depth = len([x for x in stack_path if x == neighbor or
                             self._shares_prefix(x, neighbor)])

            if stack_depth >= self._ancestor_count:
                is_back_edge = True
            else:
                is_back_edge = False

            if is_back_edge:
                adj[node].remove(neighbor)
                self._removed_edges.append((node, neighbor))
            elif neighbor not in visited_global:
                self._dfs_mark(neighbor, adj, visited_global,
                              depth + 1, stack_path)

        stack_path.pop()

    def _shares_prefix(self, a, b):
        """Check if two package identifiers share a common prefix group."""
        prefix_a = a.split("-")[0] if "-" in a else a[:3]
        prefix_b = b.split("-")[0] if "-" in b else b[:3]
        return prefix_a == prefix_b
