import json
import os

REPORT_PATH = "/app/runtime/output/transform_report.json"
MANIFEST_PATH = "/app/runtime/output/rewrite_manifest.json"


def _load_report():
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


def _load_manifest():
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)


class TestEasy:
    """Structural validation tests - verify output format and basic content."""

    def test_output_files_exist(self):
        assert os.path.isfile(REPORT_PATH), "transform_report.json not found"
        assert os.path.isfile(MANIFEST_PATH), "rewrite_manifest.json not found"

    def test_report_structure(self):
        report = _load_report()
        required_keys = [
            "project_id",
            "total_files",
            "rules_applied",
            "active_rules",
            "scope_depth",
            "files_processed",
            "integrity_hash",
        ]
        for key in required_keys:
            assert key in report, f"missing key: {key}"

    def test_manifest_has_operations(self):
        manifest = _load_manifest()
        assert "operations" in manifest, "manifest missing operations array"
        assert len(manifest["operations"]) >= 5, "insufficient operations generated"

    def test_operation_fields(self):
        manifest = _load_manifest()
        required_fields = ["file", "line", "rule", "action", "target", "scope_depth"]
        for op in manifest["operations"]:
            for field in required_fields:
                assert field in op, f"operation missing field: {field}"


class TestMedium:
    """Aggregate validation tests - verify computed values match expected state."""

    def test_active_rules_count(self):
        report = _load_report()
        assert report["active_rules"] == 4, "transform report diverges from expected state"

    def test_scope_depth_value(self):
        report = _load_report()
        assert report["scope_depth"] == 3, "scope resolution does not match bounded configuration"

    def test_gamma_symbol_resolution(self):
        report = _load_report()
        gamma = report["files_processed"]["source_gamma.src"]
        assert gamma["symbols_resolved"] == 12, "symbol resolution diverges from expected state"


class TestHard:
    """Cross-concern consistency tests - verify deterministic output with full integrity."""

    def test_operation_ordering(self):
        manifest = _load_manifest()
        operations = manifest["operations"]
        for i in range(len(operations) - 1):
            curr = operations[i]
            nxt = operations[i + 1]
            if curr["file"] == nxt["file"]:
                curr_key = (curr["line"], curr["rule"])
                nxt_key = (nxt["line"], nxt["rule"])
                assert curr_key <= nxt_key, (
                    "operations not in canonical order "
                    "(expected: line, rule_name, priority)"
                )

    def test_report_integrity_hash(self):
        report = _load_report()
        assert report["integrity_hash"] == "8c331c1029186100", (
            "integrity hash mismatch - report state is non-deterministic"
        )

    def test_full_consistency(self):
        report = _load_report()
        gamma = report["files_processed"]["source_gamma.src"]
        has_dead = any(
            f["dead_eliminated"] > 0
            for f in report["files_processed"].values()
        )
        assert has_dead, "dead code elimination not active"
        assert report["scope_depth"] == 3, "scope depth inconsistent"
        assert gamma["transforms"] == 11, "gamma transform count diverges from expected"
