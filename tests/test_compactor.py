"""Graduated test suite for the time-series compaction engine.

Tests are organized by difficulty:
- Easy (1-4): Structural validation that passes regardless of processing bugs
- Medium (5-7): Semantic checks requiring collector filter and tier fixes
- Hard (8-10): Cross-concern consistency requiring all defects resolved
"""
import json
import hashlib
import os
import subprocess
import sys

import pytest


@pytest.fixture(scope="session", autouse=True)
def run_compactor():
    """Ensure the compaction engine has been executed before tests run."""
    base_dir = os.environ.get("APP_DIR", "/app")
    report_path = os.path.join(base_dir, "runtime", "output", "compaction_report.json")
    series_path = os.path.join(base_dir, "runtime", "output", "compacted_series.json")
    
    if not os.path.exists(report_path) or not os.path.exists(series_path):
        subprocess.run(
            [sys.executable, "-m", "runtime.run_compactor"],
            cwd=base_dir,
            check=True
        )


@pytest.fixture
def report():
    """Load the compaction report."""
    base_dir = os.environ.get("APP_DIR", "/app")
    path = os.path.join(base_dir, "runtime", "output", "compaction_report.json")
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def series():
    """Load the compacted series output."""
    base_dir = os.environ.get("APP_DIR", "/app")
    path = os.path.join(base_dir, "runtime", "output", "compacted_series.json")
    with open(path) as f:
        return json.load(f)


# --- Easy Tests (always pass) ---

class TestStructuralValidation:
    """Basic structural checks on compaction output."""
    
    def test_01_report_has_required_fields(self, report):
        """Verify the compaction report contains all required fields."""
        required = [
            "engine_id", "total_collectors", "active_collectors",
            "retention_tiers", "alignment_offset_ms", "points_ingested",
            "points_compacted", "tier_stats", "integrity_hash"
        ]
        for field in required:
            assert field in report, f"Missing required field: {field}"
    
    def test_02_series_output_structure(self, series):
        """Verify series output has correct top-level structure."""
        assert "series_hash" in series
        assert "points" in series
        assert isinstance(series["points"], list)
        assert len(series["points"]) > 0
        
        # Each point has required fields
        point = series["points"][0]
        required_point_fields = ["ts", "collector", "metric", "value", "tier", "window_start"]
        for field in required_point_fields:
            assert field in point, f"Point missing field: {field}"
    
    def test_03_engine_identity(self, report):
        """Verify engine identification metadata."""
        assert report["engine_id"] == "tsdb-compact-v3"
        assert report["total_collectors"] == 4
        assert report["retention_tiers"] == 3
    
    def test_04_tier_structure(self, report):
        """Verify retention tier configuration in output."""
        tier_stats = report["tier_stats"]
        assert "raw" in tier_stats
        assert "medium" in tier_stats
        assert "coarse" in tier_stats
        
        assert tier_stats["raw"]["window_ms"] == 1000
        assert tier_stats["medium"]["window_ms"] == 60000
        assert tier_stats["coarse"]["window_ms"] == 300000
        
        # Each tier must produce at least one point
        for tier_name, stats in tier_stats.items():
            assert stats["points"] > 0, f"Tier {tier_name} produced no points"


# --- Medium Tests (require 2-3 bug fixes) ---

class TestSemanticCorrectness:
    """Semantic validation requiring correct processing logic."""
    
    def test_05_collector_ingestion_count(self, report):
        """Verify all registered active collectors contribute metrics."""
        assert report["points_ingested"] == 67, (
            f"Expected 67 ingested points from all active collectors, "
            f"got {report['points_ingested']}"
        )
    
    def test_06_alignment_offset_value(self, report):
        """Verify the alignment offset uses precise windowing configuration."""
        assert report["alignment_offset_ms"] == 0, (
            f"Alignment offset should be 0 for precise bucket boundaries, "
            f"got {report['alignment_offset_ms']}"
        )
    
    def test_07_coarse_tier_independence(self, report, series):
        """Verify coarse tier aggregation bounds are independent of other tiers."""
        coarse_points = [p for p in series["points"] if p["tier"] == "coarse"]
        assert len(coarse_points) == 6, (
            f"Expected 6 coarse tier points with independent aggregation, "
            f"got {len(coarse_points)}"
        )
        
        # Coarse tier values must reflect only their own window aggregation
        cpu_coarse = [p for p in coarse_points if p["collector"] == "cpu_host"]
        for p in cpu_coarse:
            assert 30.0 <= p["value"] <= 60.0, (
                f"Coarse cpu_usage value {p['value']} outside expected "
                f"independent aggregation range [30, 60]"
            )


# --- Hard Tests (require 4-5 bug fixes) ---

class TestCrossConsistency:
    """Cross-concern consistency requiring all defects resolved."""
    
    def test_08_deterministic_sort_ordering(self, series):
        """Verify points follow deterministic composite key ordering.
        
        Points at the same timestamp must be ordered by collector
        identifier then metric name for reproducible output.
        """
        points = series["points"]
        
        # Must have all three collectors in output for valid ordering test
        collectors_present = set(p["collector"] for p in points)
        assert len(collectors_present) == 3, (
            f"Expected 3 collectors for ordering validation, "
            f"got {len(collectors_present)}: {collectors_present}"
        )
        
        # Check that sort is by (ts, collector, metric)
        for i in range(len(points) - 1):
            curr = points[i]
            nxt = points[i + 1]
            
            curr_key = (curr["ts"], curr["collector"], curr["metric"])
            nxt_key = (nxt["ts"], nxt["collector"], nxt["metric"])
            
            assert curr_key <= nxt_key, (
                f"Sort order violation at index {i}: "
                f"{curr_key} should come before {nxt_key}. "
                f"Deterministic ordering uses (timestamp, collector_id, metric_name) "
                f"composite key."
            )
    
    def test_09_integrity_hash_verification(self, report):
        """Verify the integrity hash matches the expected canonical state.
        
        The hash encodes the complete processing state. All computation
        paths must produce correct values for the hash to match.
        """
        # Recompute hash from report fields
        hashable = {k: v for k, v in report.items() if k != "integrity_hash"}
        canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
        computed_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        
        assert report["integrity_hash"] == computed_hash, (
            f"Integrity hash mismatch: stored={report['integrity_hash']}, "
            f"computed={computed_hash}"
        )
        
        # Verify the hash corresponds to correct processing state
        assert computed_hash == "761c0818dcdebf13", (
            f"Integrity hash {computed_hash} does not match expected "
            f"canonical state hash"
        )
    
    def test_10_full_system_consistency(self, report, series):
        """Verify cross-concern consistency across the complete system.
        
        Validates that collector filtering, alignment, tier processing,
        and ordering all produce a coherent final state.
        """
        # All active collectors must appear in output
        collectors_in_output = set(p["collector"] for p in series["points"])
        assert "net_host" in collectors_in_output, (
            "net_host collector missing from output series"
        )
        assert len(collectors_in_output) == 3, (
            f"Expected 3 distinct collectors in output, "
            f"got {len(collectors_in_output)}: {collectors_in_output}"
        )
        
        # Alignment must be zero for precise windowing
        assert report["alignment_offset_ms"] == 0
        
        # Total compacted points must match sum of tier points
        total_from_tiers = sum(
            stats["points"] for stats in report["tier_stats"].values()
        )
        assert report["points_compacted"] == total_from_tiers
        assert report["points_compacted"] == 92, (
            f"Expected 92 total compacted points, got {report['points_compacted']}"
        )
        
        # Series hash must be consistent
        series_canonical = json.dumps(
            series["points"], sort_keys=True, separators=(",", ":")
        )
        expected_series_hash = hashlib.sha256(
            series_canonical.encode()
        ).hexdigest()[:16]
        assert series["series_hash"] == expected_series_hash
