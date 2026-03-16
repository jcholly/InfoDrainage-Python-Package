"""CLI validation tests for iddx_core.

Tests the iddx CLI commands: summary, pipes, validate, compare.
"""

from __future__ import annotations

import csv
import subprocess
import sys

import pytest
from pathlib import Path

from iddx_core.cli import main as cli_main, build_parser


# ============================================================================
# Helpers
# ============================================================================

def _run_cli(args: list[str], expect_success: bool = True) -> tuple[int, str, str]:
    """Run the CLI via subprocess and capture output."""
    result = subprocess.run(
        [sys.executable, "-m", "iddx_core.cli"] + args,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if expect_success:
        assert result.returncode == 0, (
            f"CLI exited with code {result.returncode}.\n"
            f"stdout: {result.stdout[:500]}\n"
            f"stderr: {result.stderr[:500]}"
        )
    return result.returncode, result.stdout, result.stderr


# ============================================================================
# iddx summary
# ============================================================================

class TestCliSummary:
    """iddx summary should produce readable output for valid models."""

    def test_summary_produces_output(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        code, stdout, stderr = _run_cli(["summary", str(model_path)])
        assert len(stdout) > 0, "summary produced no output"
        assert "Phase:" in stdout or "Phases:" in stdout, (
            "summary output missing phase information"
        )

    def test_summary_shows_model_name(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        _, stdout, _ = _run_cli(["summary", str(model_path)])
        assert model_path.name in stdout, (
            f"Model filename '{model_path.name}' not in summary output"
        )

    def test_summary_shows_counts(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        _, stdout, _ = _run_cli(["summary", str(model_path)])
        for keyword in ("Catchments:", "Junctions:", "Connections:"):
            assert keyword in stdout, (
                f"'{keyword}' not found in summary output"
            )


# ============================================================================
# iddx pipes
# ============================================================================

class TestCliPipes:
    """iddx pipes should produce valid pipe schedule output."""

    def test_pipes_console_output(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        _, stdout, _ = _run_cli(["pipes", str(model_path)])
        assert "Pipe Schedule" in stdout or "connections total" in stdout, (
            "Pipe schedule output not found"
        )

    def test_pipes_csv_export(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        csv_out = tmp_path / "pipes.csv"
        _run_cli(["pipes", str(model_path), "--csv", str(csv_out)])
        assert csv_out.exists(), "CSV file was not created"
        with open(csv_out, newline="") as f:
            reader = csv.reader(f)
            headers = next(reader)
            expected = [
                "Label", "Type", "From", "To", "Length",
                "Diameter_mm", "Diameter_in", "Manning_n", "Slope",
            ]
            for col in expected:
                assert col in headers, (
                    f"Expected column '{col}' not in CSV headers: {headers}"
                )

    def test_pipes_csv_has_data_rows(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        csv_out = tmp_path / "pipes_data.csv"
        _run_cli(["pipes", str(model_path), "--csv", str(csv_out)])
        with open(csv_out, newline="") as f:
            rows = list(csv.reader(f))
        from iddx_core import IddxModel
        model = IddxModel.open(model_path)
        phase = next(iter(model.phases.values()))
        expected_count = len(phase.connections)
        actual_count = len(rows) - 1  # minus header
        assert actual_count == expected_count, (
            f"CSV has {actual_count} data rows, expected {expected_count} connections"
        )


# ============================================================================
# iddx validate
# ============================================================================

class TestCliValidate:
    """iddx validate should catch known model issues."""

    def test_validate_runs_without_crash(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        code, stdout, stderr = _run_cli(
            ["validate", str(model_path)], expect_success=False
        )
        assert "Validation Report" in stdout, (
            "validate output missing 'Validation Report' header"
        )

    def test_validate_reports_errors_or_passes(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        _, stdout, _ = _run_cli(
            ["validate", str(model_path)], expect_success=False
        )
        has_findings = "error(s)" in stdout or "warning(s)" in stdout
        has_pass = "All checks passed" in stdout
        assert has_findings or has_pass, (
            "validate output lacks error/warning counts or 'All checks passed'"
        )

    def test_validate_detects_adverse_slopes(self, tmp_path):
        """Build a model with an adverse slope pipe and verify validate catches it."""
        from iddx_core import IddxModel, Junction, Connection

        model = IddxModel.new()
        phase = model.create_phase("Adverse Test")
        j1 = Junction(label="J1", cover_level=100, invert_level=95)
        j2 = Junction(label="J2", cover_level=102, invert_level=98, is_outfall=True)
        phase.add_junction(j1)
        phase.add_junction(j2)
        conn = Connection(
            label="Uphill",
            length=30.0, diameter=300,
            us_invert_level=95.0, ds_invert_level=98.0,
            us_cover_level=100.0, ds_cover_level=102.0,
            from_junction_guid=j1.guid, from_junction_label="J1",
            to_junction_guid=j2.guid, to_junction_label="J2",
        )
        phase.add_connection(conn)

        model_file = tmp_path / "adverse_test.iddx"
        model.save(model_file)

        code, stdout, _ = _run_cli(
            ["validate", str(model_file)], expect_success=False
        )
        assert "Adverse slope" in stdout or "adverse" in stdout.lower(), (
            "validate did not detect adverse slope"
        )

    def test_validate_detects_zero_area_catchment(self, tmp_path):
        from iddx_core import IddxModel, Junction, Catchment

        model = IddxModel.new()
        phase = model.create_phase("Zero Area Test")
        j = Junction(label="J1", cover_level=100, invert_level=97, is_outfall=True)
        phase.add_junction(j)
        c = Catchment(
            label="EmptyCatch", area=0.0, cv=0.8,
            to_dest_guid=j.guid, to_dest_label="J1",
        )
        phase.add_catchment(c)

        model_file = tmp_path / "zero_area_test.iddx"
        model.save(model_file)

        code, stdout, _ = _run_cli(
            ["validate", str(model_file)], expect_success=False
        )
        assert "zero" in stdout.lower() or "area" in stdout.lower(), (
            "validate did not detect zero-area catchment"
        )


# ============================================================================
# iddx compare
# ============================================================================

class TestCliCompare:
    """iddx compare should work for models with results."""

    def test_compare_runs(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        from iddx_core.results import find_results
        results = find_results(model_path)
        if not results:
            pytest.skip("No result files — compare requires results")

        code, stdout, stderr = _run_cli(
            ["compare", str(model_path)], expect_success=False
        )
        has_output = len(stdout) > 10 or len(stderr) > 10
        assert has_output, "compare produced no output at all"


# ============================================================================
# Parser / help
# ============================================================================

class TestCliParser:
    """Verify the argument parser builds correctly."""

    def test_parser_builds(self):
        parser = build_parser()
        assert parser is not None

    def test_version_flag(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_no_command_shows_help(self):
        code, stdout, stderr = _run_cli([], expect_success=False)
        assert code == 0 or "usage" in (stdout + stderr).lower()
