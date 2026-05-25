"""
Window reconciliation module.
Processes features in geographic sector windows, deduplicates overlapping
features, and computes aggregate area statistics.
"""


class WindowReconciler:
    """
    Reconciles features processed across multiple geographic windows.
    Handles deduplication when features appear in multiple windows
    and computes coverage area totals.
    """

    def __init__(self, config):
        self.config = config
        self.max_per_window = config.getint("windows", "max_features_per_window")

    def process_windows(self, sorted_features):
        """
        Process features in sector-based windows.
        Features are grouped by sector and processed sequentially.
        Returns deduplicated feature list with computed area totals.

        Each window produces a snapshot of features it contains.
        When a feature appears in multiple windows (due to sector
        boundary overlap), its area contribution is tracked across
        window snapshots.
        """
        windows = self._partition_into_windows(sorted_features)
        window_snapshots = []

        for window in windows:
            snapshot = self._process_single_window(window)
            window_snapshots.append(snapshot)

        # Reconcile across all window snapshots
        reconciled = self._reconcile_snapshots(window_snapshots)
        return reconciled, len(windows)

    def _partition_into_windows(self, features):
        """Split features into windows by sector grouping."""
        if not features:
            return []

        windows = []
        current_window = []
        current_sector = None

        for feature in features:
            sector = feature.get("_sector")
            if current_sector is None:
                current_sector = sector

            if sector != current_sector or len(current_window) >= self.max_per_window:
                if current_window:
                    windows.append(current_window)
                current_window = []
                current_sector = sector

            current_window.append(feature)

        if current_window:
            windows.append(current_window)

        return windows

    def _process_single_window(self, window_features):
        """
        Process a single window of features.
        Returns a snapshot dict mapping feature_id -> feature data.
        Last-write-wins deduplication within the window.
        """
        snapshot = {}
        for feature in window_features:
            fid = feature["id"]
            snapshot[fid] = {
                "id": fid,
                "type": feature["type"],
                "coordinates": feature["coordinates"],
                "bbox": feature.get("bbox"),
                "properties": feature["properties"],
                "area_sqm": feature["properties"].get("area_sqm", 0.0),
                "_source": feature["_source"],
                "_sector": feature["_sector"],
            }
        return snapshot

    def _reconcile_snapshots(self, window_snapshots):
        """
        Reconcile feature data across all window snapshots.
        Computes area totals for each unique feature by accumulating
        area contributions from each window snapshot that contains it.
        """
        area_totals = {}
        final_features = {}

        for snapshot in window_snapshots:
            for fid, data in snapshot.items():
                if fid not in area_totals:
                    area_totals[fid] = 0.0
                area_totals[fid] += data["area_sqm"]
                final_features[fid] = data

        # Apply reconciled area totals
        for fid, feature in final_features.items():
            feature["area_sqm"] = area_totals[fid]

        return list(final_features.values())
