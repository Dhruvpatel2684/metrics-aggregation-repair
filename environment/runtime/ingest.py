"""
Data ingestion module for spatial features.
Loads features from source JSON files, assigns sector IDs, and
prepares feature records for spatial indexing.
"""

import json
import glob
import os


class FeatureIngestor:
    """Loads and prepares features from multiple source files."""

    def __init__(self, config):
        self.config = config
        self.data_dir = config.get("sources", "data_directory")
        self.file_pattern = config.get("sources", "file_pattern")
        self.lon_multiplier = config.getint("sectors", "longitude_multiplier")
        self.sector_offset = config.getint("sectors", "base_sector_offset")

    def load_all_sources(self):
        """
        Load features from all source files matching the configured pattern.
        Files are loaded in glob-sorted order to ensure consistent behavior.
        Returns list of processed feature records with metadata.
        """
        pattern = os.path.join(self.data_dir, self.file_pattern)
        source_files = sorted(glob.glob(pattern))

        all_features = []
        for filepath in source_files:
            features = self._load_source_file(filepath)
            all_features.extend(features)

        return all_features

    def _load_source_file(self, filepath):
        """Load and tag features from a single source file."""
        with open(filepath, "r") as f:
            data = json.load(f)

        source_name = data["source_name"]
        source_priority = data.get("source_priority", 0)
        features = []

        for raw_feature in data["features"]:
            feature = {
                "id": raw_feature["id"],
                "type": raw_feature["type"],
                "coordinates": raw_feature["coordinates"],
                "properties": raw_feature.get("properties", {}),
                "_source": source_name,
                "_source_priority": source_priority,
            }
            features.append(feature)

        return features

    def assign_sectors(self, features):
        """
        Assign each feature to a geographic sector based on its representative
        longitude coordinate. Sectors are integer IDs derived from the longitude
        using the configured multiplier.

        Also assigns the sequence number from properties for sort ordering.
        """
        for feature in features:
            lon = self._representative_longitude(feature)
            sector_id = int(lon * self.lon_multiplier) + self.sector_offset
            feature["_sector"] = sector_id
            feature["_seq"] = feature["properties"].get("seq", 0)

        return features

    def sort_into_windows(self, features):
        """
        Sort features into processing windows by sector assignment.
        Within each sector, features are ordered by sequence number for
        deterministic processing. Lower-priority sources should appear
        before higher-priority ones so that authoritative data takes
        precedence in last-write-wins deduplication.

        Returns sorted feature list ready for windowed processing.
        """
        return sorted(features, key=lambda f: (f["_sector"], f.get("_seq", 0)))

    def _representative_longitude(self, feature):
        """
        Get the representative longitude for sector assignment.
        For points, this is the coordinate directly.
        For polygons and lines, uses the centroid longitude.
        """
        geom_type = feature["type"]
        coords = feature["coordinates"]

        if geom_type == "Point":
            return coords[0]
        elif geom_type == "Polygon":
            ring = coords[0]
            return sum(p[0] for p in ring) / len(ring)
        elif geom_type == "LineString":
            return sum(p[0] for p in coords) / len(coords)
        elif geom_type == "MultiPoint":
            return sum(p[0] for p in coords) / len(coords)
        else:
            return 0.0
