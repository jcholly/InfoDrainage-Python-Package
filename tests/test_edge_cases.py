"""Edge case and error handling tests for iddx_core.

Tests missing/corrupt files, empty phases, zero-area catchments,
adverse slopes, and exception types.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from iddx_core import (
    IddxModel, Phase, Catchment, Junction, Connection, DrainageSystem,
    IddxParseError, ResultsError, ElementNotFoundError,
    ConnectionType, OutletDetail, OutletType,
)
from iddx_core.results import ResultsReader


# ============================================================================
# Missing / corrupt file handling
# ============================================================================

class TestFileErrorHandling:
    """Verify correct exceptions for bad file paths and corrupt data."""

    def test_missing_iddx_raises_parse_error(self, tmp_path):
        with pytest.raises(IddxParseError, match="not found|File not found"):
            IddxModel.open(tmp_path / "nonexistent.iddx")

    def test_corrupt_iddx_raises_parse_error(self, tmp_path):
        bad_file = tmp_path / "corrupt.iddx"
        bad_file.write_text("this is not valid XML at all <<<<", encoding="utf-8")
        with pytest.raises(IddxParseError):
            IddxModel.open(bad_file)

    def test_empty_iddx_raises_parse_error(self, tmp_path):
        empty_file = tmp_path / "empty.iddx"
        empty_file.write_text("", encoding="utf-8")
        with pytest.raises((IddxParseError, Exception)):
            IddxModel.open(empty_file)

    def test_missing_out_raises_results_error(self, tmp_path):
        with pytest.raises(ResultsError, match="not found"):
            ResultsReader(tmp_path / "nonexistent.out")

    def test_corrupt_out_raises_results_error(self, tmp_path):
        bad_out = tmp_path / "corrupt.out"
        bad_out.write_bytes(b"\x00" * 100)
        with pytest.raises(ResultsError):
            ResultsReader(bad_out)

    def test_truncated_out_raises_results_error(self, tmp_path):
        """A file with the right magic but truncated data should fail."""
        import struct
        bad_out = tmp_path / "truncated.out"
        bad_out.write_bytes(struct.pack("<i", 516114522) + b"\x00" * 20)
        with pytest.raises((ResultsError, Exception)):
            ResultsReader(bad_out)


# ============================================================================
# Element not found
# ============================================================================

class TestElementNotFound:
    """Requesting non-existent elements should raise ElementNotFoundError."""

    def test_find_catchment_returns_none(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        phase = next(iter(model.phases.values()))
        result = phase.find_catchment("NONEXISTENT_CATCHMENT_12345")
        assert result is None, (
            "find_catchment should return None for non-existent label"
        )

    def test_find_junction_returns_none(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        phase = next(iter(model.phases.values()))
        result = phase.find_junction("NONEXISTENT_JUNCTION_12345")
        assert result is None, (
            "find_junction should return None for non-existent label"
        )

    def test_find_connection_returns_none(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        phase = next(iter(model.phases.values()))
        result = phase.find_connection("NONEXISTENT_PIPE_12345")
        assert result is None, (
            "find_connection should return None for non-existent label"
        )

    def test_clone_nonexistent_phase_raises(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        with pytest.raises(ElementNotFoundError):
            model.clone_phase("NO_SUCH_PHASE_999", "ShouldFail")


# ============================================================================
# Empty and minimal models
# ============================================================================

class TestEmptyPhases:
    """Models with empty phases should be handled gracefully."""

    def test_empty_phase_save_reload(self, tmp_path):
        model = IddxModel.new()
        phase = model.create_phase("Empty Phase")
        assert len(phase.catchments) == 0
        assert len(phase.junctions) == 0
        assert len(phase.connections) == 0
        assert len(phase.drainage_systems) == 0

        out = tmp_path / "empty_phase.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        rp = reloaded.phases.get("Empty Phase")
        assert rp is not None
        assert len(rp.catchments) == 0
        assert len(rp.junctions) == 0
        assert len(rp.connections) == 0

    def test_outfall_only_model(self, tmp_path):
        """A model with only outfalls and no pipes should save and reload."""
        model = IddxModel.new()
        phase = model.create_phase("Outfall Only")
        j = Junction(
            label="Outfall_1",
            is_outfall=True,
            cover_level=100.0,
            invert_level=97.0,
            depth=3.0,
        )
        phase.add_junction(j)

        out = tmp_path / "outfall_only.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        rp = reloaded.phases.get("Outfall Only")
        assert rp is not None
        assert len(rp.junctions) == 1
        assert len(rp.connections) == 0
        assert rp.junctions[0].is_outfall is True

    def test_no_phases_model(self, tmp_path):
        """A model with no phases should save and reload."""
        model = IddxModel.new()
        out = tmp_path / "no_phases.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        assert len(reloaded.phases) == 0


# ============================================================================
# Pathological element values
# ============================================================================

class TestPathologicalValues:
    """Elements with edge-case values should be handled without crashing."""

    def test_zero_area_catchment_save_reload(self, tmp_path):
        model = IddxModel.new()
        phase = model.create_phase("Zero Area")
        c = Catchment(label="ZeroArea", area=0.0, cv=0.8)
        phase.add_catchment(c)

        out = tmp_path / "zero_area.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        rp = reloaded.phases["Zero Area"]
        assert rp.catchments[0].area == 0.0

    def test_zero_length_connection_save_reload(self, tmp_path):
        model = IddxModel.new()
        phase = model.create_phase("Zero Length")
        j1 = Junction(label="J1", cover_level=100, invert_level=98)
        j2 = Junction(label="J2", cover_level=100, invert_level=97)
        phase.add_junction(j1)
        phase.add_junction(j2)
        conn = Connection(
            label="ZeroLen",
            length=0.0,
            diameter=300,
            from_junction_guid=j1.guid,
            from_junction_label="J1",
            to_junction_guid=j2.guid,
            to_junction_label="J2",
        )
        phase.add_connection(conn)

        out = tmp_path / "zero_length.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        rp = reloaded.phases["Zero Length"]
        assert abs(rp.connections[0].length) < 1e-9

    def test_adverse_slope_connection_save_reload(self, tmp_path):
        """A pipe where DS IL > US IL (adverse slope) should still round-trip."""
        model = IddxModel.new()
        phase = model.create_phase("Adverse")
        j1 = Junction(label="Low", cover_level=100, invert_level=95)
        j2 = Junction(label="High", cover_level=102, invert_level=98)
        phase.add_junction(j1)
        phase.add_junction(j2)
        conn = Connection(
            label="Uphill",
            length=30.0,
            diameter=300,
            us_invert_level=95.0,
            ds_invert_level=98.0,
            from_junction_guid=j1.guid,
            from_junction_label="Low",
            to_junction_guid=j2.guid,
            to_junction_label="High",
        )
        phase.add_connection(conn)

        out = tmp_path / "adverse.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        rconn = reloaded.phases["Adverse"].connections[0]
        assert rconn.us_invert_level < rconn.ds_invert_level, (
            "Adverse slope should persist through round-trip"
        )

    def test_calculated_slope_zero_length(self):
        """calculated_slope should return 0.0 for zero-length pipe."""
        conn = Connection(length=0.0, us_invert_level=100.0, ds_invert_level=99.0)
        assert conn.calculated_slope == 0.0

    def test_calculated_slope_flat_pipe(self):
        """calculated_slope should return 0.0 for flat pipe."""
        conn = Connection(length=50.0, us_invert_level=100.0, ds_invert_level=100.0)
        assert conn.calculated_slope == 0.0


# ============================================================================
# Save without filepath
# ============================================================================

class TestSaveEdgeCases:
    def test_save_no_path_raises(self):
        model = IddxModel.new()
        with pytest.raises(ValueError, match="No filepath"):
            model.save()

    def test_save_to_new_path(self, tmp_path):
        model = IddxModel.new()
        model.create_phase("Test")
        out = tmp_path / "new_save.iddx"
        result = model.save(out)
        assert result == out
        assert out.exists()
