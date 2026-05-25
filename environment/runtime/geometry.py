"""Bounding box computation and geometric utilities for spatial features."""

import math


def compute_feature_bounds(feature):
    """Compute the bounding box for a geographic feature.

    Returns a tuple (min_x, min_y, max_x, max_y) representing the
    axis-aligned bounding box of the feature geometry.

    For Point features, the bounds collapse to the point itself.
    For Polygon features, the bounds encompass the full extent of
    the outer ring coordinates.
    """
    geom = feature["geometry"]

    if geom["type"] == "Point":
        lon, lat = geom["coordinates"]
        return (lon, lat, lon, lat)

    elif geom["type"] == "Polygon":
        outer_ring = geom["coordinates"][0]
        lons = [coord[0] for coord in outer_ring]
        lats = [coord[1] for coord in outer_ring]
        min_lon = min(lons)
        max_lon = max(lons)
        min_lat = min(lats)
        max_lat = max(lats)
        return (min_lat, min_lon, max_lat, max_lon)

    else:
        raise ValueError(f"Unsupported geometry type: {geom['type']}")


def bounds_intersect(a, b):
    """Check if two bounding boxes intersect.

    Each box is a tuple (min_x, min_y, max_x, max_y).
    Returns True if the boxes overlap or touch.
    """
    if a[2] < b[0] or b[2] < a[0]:
        return False
    if a[3] < b[1] or b[3] < a[1]:
        return False
    return True


def expand_bounds(current, addition):
    """Expand a bounding box to include another box.

    Returns the minimal bounding box containing both inputs.
    If current is None, returns the addition unchanged.
    """
    if current is None:
        return addition
    return (
        min(current[0], addition[0]),
        min(current[1], addition[1]),
        max(current[2], addition[2]),
        max(current[3], addition[3]),
    )


def bounds_contain_point(bounds, lon, lat):
    """Check if a point falls within a bounding box."""
    return (bounds[0] <= lon <= bounds[2]) and (bounds[1] <= lat <= bounds[3])


def compute_distance(lon1, lat1, lon2, lat2):
    """Compute approximate distance between two points in degrees."""
    return math.sqrt((lon2 - lon1) ** 2 + (lat2 - lat1) ** 2)
