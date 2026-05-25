"""Range query execution against a spatial index."""

import configparser

from runtime.geometry import compute_feature_bounds
from runtime.rtree import SpatialIndex


class QueryEngine:
    """Executes spatial range queries using the R-tree index.

    Builds a query bounding box around a center point using a configured
    search radius, then retrieves all features intersecting that region.
    """

    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        self.center_lon = self.config.getfloat("query", "center_lon")
        self.center_lat = self.config.getfloat("query", "center_lat")
        self.radius = self.config.getfloat("query", "search_radius_km", fallback=50.0)
        self.page_size = self.config.getint("query", "results_per_page", fallback=50)

    def build_query_bounds(self):
        """Construct the axis-aligned bounding box for the range query.

        The query region is a square centered on (center_lon, center_lat)
        with half-width equal to the search radius in coordinate units.
        """
        return (
            self.center_lon - self.radius,
            self.center_lat - self.radius,
            self.center_lon + self.radius,
            self.center_lat + self.radius,
        )

    def execute(self, spatial_index):
        """Run the range query against the provided spatial index.

        Returns a list of features found within the query region, limited
        to the configured page size.
        """
        query_bounds = self.build_query_bounds()
        results = spatial_index.query_range(query_bounds)

        if len(results) > self.page_size:
            results = results[:self.page_size]

        return results, query_bounds
