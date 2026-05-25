"""Repair script for the spatial indexing pipeline.

Patches four defects in the runtime modules:
1. geometry.py - Polygon centroid coordinate order (lat/lon swap)
2. ingest.py - Deduplication key extraction for gamma source ID format
3. query_engine.py - Config key name mismatch for search radius
4. export.py - Feature count uses pre-dedup total instead of actual count
"""

import os


def patch_geometry():
    """Fix polygon bounds to use correct (lon, lat) coordinate order."""
    filepath = "/app/runtime/geometry.py"
    with open(filepath, "r") as fh:
        content = fh.read()

    content = content.replace(
        "return (min_lat, min_lon, max_lat, max_lon)",
        "return (min_lon, min_lat, max_lon, max_lat)",
    )

    with open(filepath, "w") as fh:
        fh.write(content)


def patch_ingest():
    """Fix deduplication key extraction for varying ID formats.

    poi_10001_a -> numeric part is parts[1] = '10001'
    gamma_poi_20001 -> numeric part is parts[2] = '20001'

    Use the last numeric segment as the dedup key.
    """
    filepath = "/app/runtime/ingest.py"
    with open(filepath, "r") as fh:
        content = fh.read()

    old_func = '''def extract_dedup_key(feature):
    """Extract numeric identifier for deduplication across sources.

    Features from different sources describing the same geographic entity
    share a numeric ID component. The ID format uses underscore separation
    with the numeric portion in the second segment.

    Examples:
        poi_10001_a -> 10001
        poi_10001_b -> 10001
        gamma_poi_20001 -> poi
    """
    feature_id = feature["id"]
    parts = feature_id.split("_")
    return parts[1]'''

    new_func = '''def extract_dedup_key(feature):
    """Extract numeric identifier for deduplication across sources.

    Features from different sources describing the same geographic entity
    share a numeric ID component. Extract the numeric segment regardless
    of prefix format.

    Examples:
        poi_10001_a -> 10001
        poi_10001_b -> 10001
        gamma_poi_20001 -> 20001
    """
    feature_id = feature["id"]
    parts = feature_id.split("_")
    for part in parts:
        if part.isdigit():
            return part
    return feature_id'''

    content = content.replace(old_func, new_func)

    with open(filepath, "w") as fh:
        fh.write(content)


def patch_query_engine():
    """Fix config key name for search radius parameter."""
    filepath = "/app/runtime/query_engine.py"
    with open(filepath, "r") as fh:
        content = fh.read()

    content = content.replace(
        'self.radius = self.config.getfloat("query", "search_radius_km", fallback=50.0)',
        'self.radius = self.config.getfloat("query", "search_radius_degrees", fallback=0.5)',
    )

    with open(filepath, "w") as fh:
        fh.write(content)


def patch_export():
    """Fix total_features and integrity hash computation in export module.

    Two issues:
    - total_features reports raw loaded count instead of actual output count
    - integrity_hash is computed over unsorted records instead of sorted output
    """
    filepath = "/app/runtime/export.py"
    with open(filepath, "r") as fh:
        content = fh.read()

    content = content.replace(
        '"total_features": total_features_loaded,',
        '"total_features": len(output_features),',
    )

    content = content.replace(
        "integrity_hash = compute_integrity_hash(unsorted_records)",
        "integrity_hash = compute_integrity_hash(output_features)",
    )

    with open(filepath, "w") as fh:
        fh.write(content)


def main():
    print("[repair] Patching geometry.py - coordinate order fix")
    patch_geometry()

    print("[repair] Patching ingest.py - dedup key extraction fix")
    patch_ingest()

    print("[repair] Patching query_engine.py - config key name fix")
    patch_query_engine()

    print("[repair] Patching export.py - feature count fix")
    patch_export()

    print("[repair] All patches applied, re-running pipeline")
    os.system("cd /app && python3 -m runtime.run_indexer")
    print("[repair] Done")


if __name__ == "__main__":
    main()
