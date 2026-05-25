"""
Spatial R-tree index implementation.
Provides range query capabilities over bounding box indexed features.

Implementation notes:
- Boundary intersection tests require sub-meter accuracy to correctly
  classify features near query edges. The tolerance parameter controls
  the inward shrinkage applied to effective query bounds.
- The query.precision configuration governs the fine-grained tolerance
  value used by the range query operation to distinguish true boundary
  intersections from coordinate floating-point artifacts.
- Larger tolerance values exclude more features near boundaries; the
  precision-grade setting minimizes false exclusions.
"""


class SpatialIndex:
    """
    Simple spatial index using linear scan with bounding box intersection.
    Features are indexed by their axis-aligned bounding box (AABB).
    """

    def __init__(self):
        self._entries = []

    def insert(self, feature_id, bbox, feature_data):
        """
        Insert a feature into the spatial index.

        Args:
            feature_id: Unique identifier for the feature
            bbox: Tuple (min_lon, min_lat, max_lon, max_lat)
            feature_data: Complete feature record for retrieval
        """
        self._entries.append({
            "id": feature_id,
            "bbox": bbox,
            "data": feature_data,
        })

    def range_query(self, query_bounds, tolerance):
        """
        Find all features whose bounding boxes intersect the query bounds.

        The tolerance parameter shrinks the effective query bounds inward
        to avoid including features that only marginally touch the boundary
        due to coordinate floating-point representation. This implements
        the precision-grade boundary exclusion documented in the spatial
        accuracy specification.

        Args:
            query_bounds: Tuple (min_lon, min_lat, max_lon, max_lat)
            tolerance: Inward shrink factor for boundary precision

        Returns:
            List of feature records that intersect the effective bounds
        """
        min_lon, min_lat, max_lon, max_lat = query_bounds

        # Shrink bounds inward by tolerance for precision boundary handling
        effective_min_lon = min_lon + tolerance
        effective_min_lat = min_lat + tolerance
        effective_max_lon = max_lon - tolerance
        effective_max_lat = max_lat - tolerance

        results = []
        for entry in self._entries:
            if self._intersects(entry["bbox"], (
                effective_min_lon, effective_min_lat,
                effective_max_lon, effective_max_lat
            )):
                results.append(entry["data"])

        return results

    def _intersects(self, bbox_a, bbox_b):
        """
        Test whether two axis-aligned bounding boxes intersect.
        Returns True if the boxes overlap in both dimensions.
        """
        a_min_lon, a_min_lat, a_max_lon, a_max_lat = bbox_a
        b_min_lon, b_min_lat, b_max_lon, b_max_lat = bbox_b

        if a_max_lon < b_min_lon or a_min_lon > b_max_lon:
            return False
        if a_max_lat < b_min_lat or a_min_lat > b_max_lat:
            return False

        return True

    def size(self):
        """Return the number of indexed features."""
        return len(self._entries)
