"""
Query engine for spatial range searches.
Configures search bounds and tolerance from the indexer configuration,
then executes range queries against the spatial index.
"""


class QueryEngine:
    """Executes configured spatial queries against the R-tree index."""

    def __init__(self, config, spatial_index):
        self.config = config
        self.index = spatial_index
        self._load_query_params()

    def _load_query_params(self):
        """Load query parameters from configuration."""
        self.center_lon = self.config.getfloat("query", "center_lon")
        self.center_lat = self.config.getfloat("query", "center_lat")
        self.range_deg = self.config.getfloat("query", "range_degrees")
        self.tolerance = self.config.getfloat("query", "spatial_tolerance_degrees")

    def compute_query_bounds(self):
        """
        Compute the rectangular query bounds from center + range.
        Returns (min_lon, min_lat, max_lon, max_lat).
        """
        min_lon = self.center_lon - self.range_deg
        min_lat = self.center_lat - self.range_deg
        max_lon = self.center_lon + self.range_deg
        max_lat = self.center_lat + self.range_deg
        return (min_lon, min_lat, max_lon, max_lat)

    def execute_query(self):
        """
        Execute the configured range query against the spatial index.
        Uses the tolerance setting for boundary precision control.
        Returns list of matching feature records.
        """
        bounds = self.compute_query_bounds()
        results = self.index.range_query(bounds, self.tolerance)
        return results

    def get_query_metadata(self):
        """Return metadata about the query configuration."""
        return {
            "center": [self.center_lon, self.center_lat],
            "range_degrees": self.range_deg,
            "tolerance": self.tolerance,
            "bounds": self.compute_query_bounds(),
        }
