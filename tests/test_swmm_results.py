"""SWMM binary results (.out) parsing tests for iddx_core.

Tests node/link counts, time series extraction, peak flow physical
reasonableness, and the find_results/load_results discovery functions.
"""

from __future__ import annotations

import datetime

import pytest
from pathlib import Path

from iddx_core import IddxModel
from iddx_core.results import (
    ResultsReader, find_results, load_results, build_label_map,
    TimeSeries, NodeSummary, LinkSummary,
)
from iddx_core.exceptions import ResultsError, ElementNotFoundError


# ============================================================================
# Helpers
# ============================================================================

def _find_any_out_file(model_path: Path) -> Path | None:
    """Look for any .out file associated with the model."""
    results = find_results(model_path)
    for paths in results.values():
        for p in paths:
            return p
    return None


def _collect_all_readers(model_path: Path) -> list[ResultsReader]:
    """Load every .out file for the given model."""
    readers = []
    results = find_results(model_path)
    for paths in results.values():
        for p in paths:
            readers.append(ResultsReader(p))
    return readers


# ============================================================================
# Basic parsing
# ============================================================================

class TestResultsParsing:
    """Parse .out files and verify structural properties."""

    @pytest.fixture(scope="class")
    def reader(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        out_file = _find_any_out_file(model_path)
        if out_file is None:
            pytest.skip("No .out result files found for this model")
        return ResultsReader(out_file)

    def test_node_count_positive(self, reader):
        assert len(reader.node_ids) > 0, (
            "Expected at least one node in results"
        )

    def test_link_count_positive(self, reader):
        assert len(reader.link_ids) > 0, (
            "Expected at least one link in results"
        )

    def test_periods_positive(self, reader):
        assert reader.num_periods > 0, (
            "Expected at least one reporting period"
        )

    def test_report_interval_reasonable(self, reader):
        assert 1 <= reader.report_interval_seconds <= 86400, (
            f"Report interval {reader.report_interval_seconds}s is outside "
            f"reasonable range (1s - 86400s)"
        )

    def test_start_before_end(self, reader):
        assert reader.start_time < reader.end_time, (
            f"Start time {reader.start_time} is not before end time {reader.end_time}"
        )


# ============================================================================
# Time series integrity
# ============================================================================

class TestTimeSeriesIntegrity:
    """Time series length and value sanity checks."""

    @pytest.fixture(scope="class")
    def reader(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        out_file = _find_any_out_file(model_path)
        if out_file is None:
            pytest.skip("No .out result files found")
        return ResultsReader(out_file)

    def test_node_time_series_length(self, reader):
        """Time series length must equal num_periods."""
        if not reader.node_ids:
            pytest.skip("No nodes")
        nid = reader.node_ids[0]
        ts = reader.node_time_series(nid, "total_inflow")
        assert len(ts.values) == reader.num_periods, (
            f"Node time series has {len(ts.values)} values, "
            f"expected {reader.num_periods}"
        )
        assert len(ts.times) == reader.num_periods

    def test_link_time_series_length(self, reader):
        if not reader.link_ids:
            pytest.skip("No links")
        lid = reader.link_ids[0]
        ts = reader.link_time_series(lid, "flow_rate")
        assert len(ts.values) == reader.num_periods

    def test_system_time_series_length(self, reader):
        ts = reader.system_time_series("rainfall")
        assert len(ts.values) == reader.num_periods

    def test_time_series_times_monotonically_increase(self, reader):
        if not reader.node_ids:
            pytest.skip("No nodes")
        ts = reader.node_time_series(reader.node_ids[0], "total_inflow")
        for i in range(1, len(ts.times)):
            assert ts.times[i] > ts.times[i - 1], (
                f"Time series not monotonic at index {i}: "
                f"{ts.times[i-1]} >= {ts.times[i]}"
            )


# ============================================================================
# Physical reasonableness
# ============================================================================

class TestPhysicalReasonableness:
    """Peak values should be physically plausible."""

    @pytest.fixture(scope="class")
    def reader(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        out_file = _find_any_out_file(model_path)
        if out_file is None:
            pytest.skip("No .out result files found")
        return ResultsReader(out_file)

    def test_peak_flows_non_negative(self, reader):
        """Peak flows in links should be non-negative (absolute value)."""
        for lid in reader.link_ids:
            ls = reader.link_summary(lid)
            assert abs(ls.peak_flow) >= 0, (
                f"Link '{lid}': peak_flow is NaN or invalid"
            )

    def test_peak_depths_non_negative(self, reader):
        for nid in reader.node_ids:
            ns = reader.node_summary(nid)
            assert ns.peak_depth >= 0, (
                f"Node '{nid}': negative peak depth {ns.peak_depth}"
            )

    def test_peak_velocities_bounded(self, reader):
        """Velocities should typically be < 50 m/s for stormwater."""
        for lid in reader.link_ids:
            ls = reader.link_summary(lid)
            assert ls.peak_velocity < 50, (
                f"Link '{lid}': peak velocity {ls.peak_velocity} m/s unreasonable"
            )

    def test_node_summaries_have_valid_types(self, reader):
        for nid in reader.node_ids:
            ns = reader.node_summary(nid)
            assert isinstance(ns.node_type, int)
            assert ns.node_type >= 0


# ============================================================================
# find_results / load_results
# ============================================================================

class TestResultsDiscovery:
    """Test the find_results() and load_results() discovery functions."""

    def test_find_results_returns_dict(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        result = find_results(model_path)
        assert isinstance(result, dict), (
            f"find_results returned {type(result)}, expected dict"
        )

    def test_find_results_paths_exist(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        result = find_results(model_path)
        for phase_name, paths in result.items():
            for p in paths:
                assert p.exists(), (
                    f"find_results reported non-existent file: {p}"
                )

    def test_load_results_readers_valid(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        results = find_results(model_path)
        if not results:
            pytest.skip("No result files found")

        loaded = load_results(model_path)
        for phase_name, rp_dict in loaded.items():
            for rp, reader in rp_dict.items():
                assert isinstance(reader, ResultsReader), (
                    f"Expected ResultsReader, got {type(reader)}"
                )
                assert reader.num_periods > 0

    def test_load_results_with_model(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        results = find_results(model_path)
        if not results:
            pytest.skip("No result files found")

        model = IddxModel.open(model_path)
        loaded = load_results(model_path, model=model)
        assert isinstance(loaded, dict)

    def test_build_label_map_contains_guids(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        lmap = build_label_map(model)
        assert isinstance(lmap, dict)
        for _, phase in model.phases.items():
            for j in phase.junctions:
                if j.guid:
                    assert j.guid in lmap, (
                        f"Junction GUID '{j.guid}' missing from label map"
                    )


# ============================================================================
# Error handling for results
# ============================================================================

class TestResultsErrors:
    """Results reader should raise proper exceptions for bad IDs."""

    @pytest.fixture(scope="class")
    def reader(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        out_file = _find_any_out_file(model_path)
        if out_file is None:
            pytest.skip("No .out result files found")
        return ResultsReader(out_file)

    def test_bad_node_id_raises(self, reader):
        with pytest.raises(ElementNotFoundError):
            reader.node_time_series("FAKE_NODE_ID_999")

    def test_bad_link_id_raises(self, reader):
        with pytest.raises(ElementNotFoundError):
            reader.link_time_series("FAKE_LINK_ID_999")

    def test_bad_variable_raises(self, reader):
        if not reader.node_ids:
            pytest.skip("No nodes")
        with pytest.raises(KeyError):
            reader.node_time_series(reader.node_ids[0], "nonexistent_variable")

    def test_bad_system_variable_raises(self, reader):
        with pytest.raises(KeyError):
            reader.system_time_series("nonexistent_sys_var")


# ============================================================================
# TimeSeries properties
# ============================================================================

class TestTimeSeriesProperties:
    """Verify TimeSeries computed properties."""

    def test_peak_of_known_values(self):
        ts = TimeSeries(
            element_id="test", element_label="Test",
            variable="flow",
            times=[datetime.datetime(2024, 1, 1, i) for i in range(5)],
            values=[1.0, 3.0, 5.0, 2.0, 0.5],
        )
        assert ts.peak == 5.0
        assert ts.min == 0.5
        assert abs(ts.mean - 2.3) < 1e-6
        assert abs(ts.total - 11.5) < 1e-6
        assert ts.peak_time == datetime.datetime(2024, 1, 1, 2)

    def test_empty_timeseries(self):
        ts = TimeSeries(
            element_id="empty", element_label="Empty",
            variable="flow", times=[], values=[],
        )
        assert ts.peak == 0.0
        assert ts.min == 0.0
        assert ts.mean == 0.0
        assert ts.peak_time is None
