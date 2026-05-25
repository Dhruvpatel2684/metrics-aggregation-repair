"""
Export module for spatial index results.
Writes feature records and coverage reports with integrity verification.
"""

import json
import hashlib
import os


class ReportExporter:
    """Exports processed spatial features and coverage reports."""

    def __init__(self, config):
        self.config = config
        self.output_dir = config.get("export", "output_directory")
        self.features_file = config.get("export", "features_file")
        self.report_file = config.get("export", "report_file")
        self.sort_output = config.getboolean("export", "sort_output")

    def export_features(self, features):
        """
        Write feature records to JSONL output file.
        If sort_output is enabled, features are sorted by ID before writing.
        Returns the list of exported features (in output order).
        """
        if self.sort_output:
            features = sorted(features, key=lambda f: f["id"])

        output_path = os.path.join(self.output_dir, self.features_file)
        with open(output_path, "w") as f:
            for feature in features:
                record = {
                    "id": feature["id"],
                    "type": feature["type"],
                    "bbox": feature.get("bbox"),
                    "area_sqm": feature.get("area_sqm", 0.0),
                    "source": feature.get("_source", "unknown"),
                    "sector": feature.get("_sector", -1),
                    "properties": feature.get("properties", {}),
                }
                f.write(json.dumps(record, sort_keys=True) + "\n")

        return features

    def export_report(self, features, query_results, window_count, query_meta):
        """
        Write the coverage report with integrity hash.
        The hash is computed over sorted feature records to ensure
        deterministic verification.
        """
        # Compute integrity hash over sorted feature output
        hasher = hashlib.sha256()
        for feature in sorted(features, key=lambda f: f["id"]):
            entry = f"{feature['id']}:{feature['type']}:{feature.get('area_sqm', 0.0)}"
            hasher.update(entry.encode("utf-8"))
        integrity_hash = hasher.hexdigest()

        # Compute source distribution
        source_counts = {}
        for f in features:
            src = f.get("_source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        # Compute type distribution
        type_counts = {}
        for f in features:
            t = f.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        report = {
            "integrity_hash": integrity_hash,
            "total_features": len(features),
            "query_result_count": len(query_results),
            "window_count": window_count,
            "source_distribution": source_counts,
            "type_distribution": type_counts,
            "query_metadata": query_meta,
            "feature_areas": {f["id"]: f.get("area_sqm", 0.0) for f in features},
        }

        output_path = os.path.join(self.output_dir, self.report_file)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)

        return report
