"""Simplified R-tree spatial index for geographic feature storage and retrieval."""

from runtime.geometry import bounds_intersect, expand_bounds


class RTreeNode:
    """A node in the R-tree, either internal or leaf."""

    def __init__(self, is_leaf=True):
        self.is_leaf = is_leaf
        self.entries = []
        self.bounds = None
        self.children = []


class SpatialIndex:
    """A simplified R-tree implementation for 2D spatial indexing.

    Features are stored in leaf nodes with their bounding boxes.
    Internal nodes contain child node references with encompassing bounds.
    """

    def __init__(self, node_capacity=8, split_min=3):
        self.node_capacity = node_capacity
        self.split_min = split_min
        self.root = RTreeNode(is_leaf=True)
        self.size = 0

    def insert(self, feature, bounds):
        """Insert a feature with its precomputed bounding box into the index."""
        entry = {"feature": feature, "bounds": bounds}
        self._insert_entry(self.root, entry)
        self.size += 1

    def _insert_entry(self, node, entry):
        """Recursively insert an entry into the appropriate leaf node."""
        if node.is_leaf:
            node.entries.append(entry)
            node.bounds = expand_bounds(node.bounds, entry["bounds"])

            if len(node.entries) > self.node_capacity:
                self._split_node(node)
        else:
            best_child = self._choose_subtree(node, entry["bounds"])
            self._insert_entry(best_child, entry)
            node.bounds = expand_bounds(node.bounds, entry["bounds"])

    def _choose_subtree(self, node, bounds):
        """Select the child node that requires least expansion to fit the entry."""
        best = None
        best_expansion = float("inf")

        for child in node.children:
            if child.bounds is None:
                return child
            expanded = expand_bounds(child.bounds, bounds)
            expansion = (
                (expanded[2] - expanded[0]) * (expanded[3] - expanded[1])
                - (child.bounds[2] - child.bounds[0]) * (child.bounds[3] - child.bounds[1])
            )
            if expansion < best_expansion:
                best_expansion = expansion
                best = child

        return best

    def _split_node(self, node):
        """Split an overflowing node into two children."""
        entries = node.entries[:]
        entries.sort(key=lambda e: e["bounds"][0])

        mid = len(entries) // 2
        left_entries = entries[:mid]
        right_entries = entries[mid:]

        left_child = RTreeNode(is_leaf=True)
        left_child.entries = left_entries
        left_child.bounds = None
        for e in left_entries:
            left_child.bounds = expand_bounds(left_child.bounds, e["bounds"])

        right_child = RTreeNode(is_leaf=True)
        right_child.entries = right_entries
        right_child.bounds = None
        for e in right_entries:
            right_child.bounds = expand_bounds(right_child.bounds, e["bounds"])

        node.is_leaf = False
        node.entries = []
        node.children = [left_child, right_child]
        node.bounds = expand_bounds(left_child.bounds, right_child.bounds)

    def query_range(self, query_bounds):
        """Find all features whose bounds intersect the query bounding box."""
        results = []
        self._query_node(self.root, query_bounds, results)
        return results

    def _query_node(self, node, query_bounds, results):
        """Recursively search the tree for intersecting features."""
        if node.bounds is None:
            return

        if not bounds_intersect(node.bounds, query_bounds):
            return

        if node.is_leaf:
            for entry in node.entries:
                if bounds_intersect(entry["bounds"], query_bounds):
                    results.append(entry["feature"])
        else:
            for child in node.children:
                self._query_node(child, query_bounds, results)

    def get_stats(self):
        """Compute tree statistics for reporting."""
        depth = self._compute_depth(self.root)
        node_count = self._count_nodes(self.root)
        return {
            "total_indexed": self.size,
            "tree_depth": depth,
            "node_count": node_count,
        }

    def _compute_depth(self, node):
        """Compute the maximum depth of the tree."""
        if node.is_leaf:
            return 1
        if not node.children:
            return 1
        return 1 + max(self._compute_depth(c) for c in node.children)

    def _count_nodes(self, node):
        """Count total nodes in the tree."""
        if node.is_leaf:
            return 1
        return 1 + sum(self._count_nodes(c) for c in node.children)
