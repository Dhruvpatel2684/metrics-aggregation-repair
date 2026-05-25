"""
Geometry validation and bounding box computation.
Handles coordinate extraction and type filtering for all supported geometries.
"""

import configparser
import os


class GeometryProcessor:
    """Processes raw feature geometries, validates types, and computes bounding boxes."""

    def __init__(self, config):
        self.config = config
        self._load_supported_types()
        self.precision = config.getint("geometry", "coordinate_precision")
        self.bbox_expansion = config.getfloat("geometry", "bbox_expansion_factor")

    def _load_supported_types(self):
        """Load the set of geometry types that this processor supports."""
        raw = self.config.get("geometry", "supported_types", fallback="")
        self._supported_types = set(raw.split(","))

    def is_supported(self, geom_type):
        """Check whether a geometry type is in the supported set."""
        return geom_type in self._supported_types

    def compute_bbox(self, feature):
        """
        Compute the axis-aligned bounding box for a feature.
        Returns (min_lon, min_lat, max_lon, max_lat) tuple.
        Supports Point, Polygon, MultiPoint, and LineString geometries.
        """
        geom_type = feature["type"]
        coords = feature["coordinates"]

        if geom_type == "Point":
            lon, lat = coords
            return (lon, lat, lon, lat)
        elif geom_type == "Polygon":
            return self._bbox_from_ring(coords[0])
        elif geom_type == "MultiPoint":
            return self._bbox_from_points(coords)
        elif geom_type == "LineString":
            return self._bbox_from_points(coords)
        else:
            return None

    def _bbox_from_points(self, points):
        """Compute bounding box from a list of [lon, lat] points."""
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        return (min(lons), min(lats), max(lons), max(lats))

    def _bbox_from_ring(self, ring):
        """Compute bounding box from a polygon ring."""
        return self._bbox_from_points(ring)

    def process_feature(self, feature):
        """
        Process a single feature: validate type, compute bbox.
        Returns processed feature dict or None if type unsupported.
        """
        geom_type = feature["type"]

        if not self.is_supported(geom_type):
            return None

        bbox = self.compute_bbox(feature)
        if bbox is None:
            return None

        return {
            "id": feature["id"],
            "type": geom_type,
            "coordinates": feature["coordinates"],
            "bbox": bbox,
            "properties": feature.get("properties", {}),
        }
