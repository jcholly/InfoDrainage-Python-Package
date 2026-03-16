"""Round-trip integrity tests for iddx_core.

Validates that opening, saving, and re-opening .iddx files preserves all
model data — element counts, field values, and newly added elements.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from iddx_core import (
    IddxModel, Phase, Catchment, Junction, Connection,
    DrainageSystem, ConnectionType, RunoffMethod, OutletDetail,
    OutletType,
)
from iddx_core.utils import new_guid


# ============================================================================
# Round-trip: element counts preserved
# ============================================================================

class TestRoundTripCounts:
    """Open → Save → Reopen cycle must preserve every element count."""

    @pytest.fixture
    def round_tripped(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        original = IddxModel.open(model_path)
        save_path = tmp_path / "round_trip.iddx"
        original.save(save_path)
        reloaded = IddxModel.open(save_path)
        return original, reloaded

    def test_phase_count(self, round_tripped):
        orig, reloaded = round_tripped
        assert len(reloaded.phases) == len(orig.phases), (
            f"Phase count changed: {len(orig.phases)} → {len(reloaded.phases)}"
        )

    def test_rainfall_source_count(self, round_tripped):
        orig, reloaded = round_tripped
        assert len(reloaded.rainfall_sources) == len(orig.rainfall_sources), (
            f"Rainfall source count changed: {len(orig.rainfall_sources)} "
            f"→ {len(reloaded.rainfall_sources)}"
        )

    def test_catchment_counts(self, round_tripped):
        orig, reloaded = round_tripped
        for label in orig.phases:
            orig_count = len(orig.phases[label].catchments)
            reload_count = len(reloaded.phases[label].catchments)
            assert reload_count == orig_count, (
                f"Phase '{label}': catchment count {orig_count} → {reload_count}"
            )

    def test_junction_counts(self, round_tripped):
        orig, reloaded = round_tripped
        for label in orig.phases:
            orig_count = len(orig.phases[label].junctions)
            reload_count = len(reloaded.phases[label].junctions)
            assert reload_count == orig_count, (
                f"Phase '{label}': junction count {orig_count} → {reload_count}"
            )

    def test_drainage_system_counts(self, round_tripped):
        orig, reloaded = round_tripped
        for label in orig.phases:
            orig_count = len(orig.phases[label].drainage_systems)
            reload_count = len(reloaded.phases[label].drainage_systems)
            assert reload_count == orig_count, (
                f"Phase '{label}': drainage system count {orig_count} → {reload_count}"
            )

    def test_connection_counts(self, round_tripped):
        orig, reloaded = round_tripped
        for label in orig.phases:
            orig_count = len(orig.phases[label].connections)
            reload_count = len(reloaded.phases[label].connections)
            assert reload_count == orig_count, (
                f"Phase '{label}': connection count {orig_count} → {reload_count}"
            )

    def test_outfall_counts(self, round_tripped):
        orig, reloaded = round_tripped
        for label in orig.phases:
            orig_outfalls = orig.phases[label].num_outfalls
            reload_outfalls = reloaded.phases[label].num_outfalls
            assert reload_outfalls == orig_outfalls, (
                f"Phase '{label}': outfall count {orig_outfalls} → {reload_outfalls}"
            )


# ============================================================================
# Round-trip: field edits persist
# ============================================================================

class TestRoundTripEdits:
    """Editing a field on a model element must survive save/reload."""

    def _open_save_reload(self, model_path, tmp_path, mutator):
        """Helper: open model, apply mutator, save, reload, return reloaded."""
        model = IddxModel.open(model_path)
        mutator(model)
        out = tmp_path / "edited.iddx"
        model.save(out)
        return IddxModel.open(out)

    def test_catchment_cv_edit(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        NEW_CV = 0.42

        orig = IddxModel.open(model_path)
        phase = next(iter(orig.phases.values()))
        if not phase.catchments:
            pytest.skip("No catchments to edit")
        target_label = phase.catchments[0].label

        def edit(m):
            p = next(iter(m.phases.values()))
            p.catchments[0].cv = NEW_CV

        reloaded = self._open_save_reload(model_path, tmp_path, edit)
        rp = next(iter(reloaded.phases.values()))
        c = rp.find_catchment(target_label)
        assert c is not None, f"Catchment '{target_label}' missing after reload"
        assert abs(c.cv - NEW_CV) < 1e-6, (
            f"Catchment CV not persisted: expected {NEW_CV}, got {c.cv}"
        )

    def test_pipe_diameter_edit(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        NEW_DIAM = 600.0

        orig = IddxModel.open(model_path)
        phase = next(iter(orig.phases.values()))
        if not phase.connections:
            pytest.skip("No connections to edit")
        target_label = phase.connections[0].label

        def edit(m):
            p = next(iter(m.phases.values()))
            p.connections[0].diameter = NEW_DIAM

        reloaded = self._open_save_reload(model_path, tmp_path, edit)
        rp = next(iter(reloaded.phases.values()))
        conn = rp.find_connection(target_label)
        assert conn is not None, f"Connection '{target_label}' missing after reload"
        assert abs(conn.diameter - NEW_DIAM) < 0.1, (
            f"Pipe diameter not persisted: expected {NEW_DIAM}, got {conn.diameter}"
        )

    def test_junction_invert_edit(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        NEW_IL = 95.123

        orig = IddxModel.open(model_path)
        phase = next(iter(orig.phases.values()))
        if not phase.junctions:
            pytest.skip("No junctions to edit")
        target_label = phase.junctions[0].label

        def edit(m):
            p = next(iter(m.phases.values()))
            p.junctions[0].invert_level = NEW_IL

        reloaded = self._open_save_reload(model_path, tmp_path, edit)
        rp = next(iter(reloaded.phases.values()))
        j = rp.find_junction(target_label)
        assert j is not None, f"Junction '{target_label}' missing after reload"
        assert abs(j.invert_level - NEW_IL) < 1e-3, (
            f"Junction IL not persisted: expected {NEW_IL}, got {j.invert_level}"
        )

    def test_mannings_n_edit(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        NEW_N = 0.015

        orig = IddxModel.open(model_path)
        phase = next(iter(orig.phases.values()))
        if not phase.connections:
            pytest.skip("No connections to edit")
        target_label = phase.connections[0].label

        def edit(m):
            p = next(iter(m.phases.values()))
            p.connections[0].mannings_n = NEW_N

        reloaded = self._open_save_reload(model_path, tmp_path, edit)
        rp = next(iter(reloaded.phases.values()))
        conn = rp.find_connection(target_label)
        assert conn is not None
        assert abs(conn.mannings_n - NEW_N) < 1e-6, (
            f"Manning's n not persisted: expected {NEW_N}, got {conn.mannings_n}"
        )


# ============================================================================
# Round-trip: newly added elements survive
# ============================================================================

class TestRoundTripAdditions:
    """Elements added via the API must appear after save/reload."""

    def test_added_junction_survives(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        phase = next(iter(model.phases.values()))

        new_j = Junction(
            label="TEST_JUNCTION_QA",
            x=100.0, y=200.0,
            cover_level=102.0,
            invert_level=99.0,
            depth=3.0,
        )
        phase.add_junction(new_j)

        out = tmp_path / "added_junction.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        rp = next(iter(reloaded.phases.values()))
        found = rp.find_junction("TEST_JUNCTION_QA")
        assert found is not None, "Added junction not found after round-trip"
        assert abs(found.cover_level - 102.0) < 1e-3
        assert abs(found.invert_level - 99.0) < 1e-3

    def test_added_catchment_survives(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        phase = next(iter(model.phases.values()))

        dest_guid = ""
        if phase.junctions:
            dest_guid = phase.junctions[0].guid

        new_c = Catchment(
            label="TEST_CATCHMENT_QA",
            area=0.005,
            cv=0.65,
            pimp=80,
            to_dest_guid=dest_guid,
        )
        phase.add_catchment(new_c)

        out = tmp_path / "added_catchment.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        rp = next(iter(reloaded.phases.values()))
        found = rp.find_catchment("TEST_CATCHMENT_QA")
        assert found is not None, "Added catchment not found after round-trip"
        assert abs(found.area - 0.005) < 1e-6
        assert abs(found.cv - 0.65) < 1e-6

    def test_added_connection_survives(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        phase = next(iter(model.phases.values()))
        if len(phase.junctions) < 2:
            pytest.skip("Need at least 2 junctions to add a connection")

        j1, j2 = phase.junctions[0], phase.junctions[1]
        new_conn = Connection(
            label="TEST_PIPE_QA",
            diameter=450.0,
            length=50.0,
            mannings_n=0.013,
            us_invert_level=100.0,
            ds_invert_level=99.5,
            from_junction_guid=j1.guid,
            from_junction_label=j1.label,
            to_junction_guid=j2.guid,
            to_junction_label=j2.label,
        )
        phase.add_connection(new_conn)

        out = tmp_path / "added_connection.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        rp = next(iter(reloaded.phases.values()))
        found = rp.find_connection("TEST_PIPE_QA")
        assert found is not None, "Added connection not found after round-trip"
        assert abs(found.diameter - 450.0) < 0.1
        assert abs(found.length - 50.0) < 0.1


# ============================================================================
# Cloned phases
# ============================================================================

class TestPhaseClone:
    """Cloned phases must contain independent copies of all elements."""

    def test_clone_has_same_element_counts(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        source_label = next(iter(model.phases))
        source = model.phases[source_label]
        cloned = model.clone_phase(source_label, "CLONE_QA")

        assert len(cloned.catchments) == len(source.catchments), (
            f"Cloned catchments: {len(source.catchments)} → {len(cloned.catchments)}"
        )
        assert len(cloned.junctions) == len(source.junctions), (
            f"Cloned junctions: {len(source.junctions)} → {len(cloned.junctions)}"
        )
        assert len(cloned.drainage_systems) == len(source.drainage_systems), (
            f"Cloned drainage systems: {len(source.drainage_systems)} "
            f"→ {len(cloned.drainage_systems)}"
        )
        assert len(cloned.connections) == len(source.connections), (
            f"Cloned connections: {len(source.connections)} → {len(cloned.connections)}"
        )

    def test_clone_is_independent(self, model_path, tmp_path):
        """Editing the clone must not alter the source phase."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        source_label = next(iter(model.phases))
        source = model.phases[source_label]

        if not source.catchments:
            pytest.skip("No catchments to test independence")

        original_cv = source.catchments[0].cv
        cloned = model.clone_phase(source_label, "CLONE_INDEP_QA")
        cloned.catchments[0].cv = 0.99

        assert abs(source.catchments[0].cv - original_cv) < 1e-9, (
            "Modifying cloned phase altered source phase — not independent"
        )

    def test_clone_different_guid(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        source_label = next(iter(model.phases))
        source = model.phases[source_label]
        cloned = model.clone_phase(source_label, "CLONE_GUID_QA")

        assert cloned.guid != source.guid, "Cloned phase has the same GUID as source"

    def test_clone_survives_save_reload(self, model_path, tmp_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        source_label = next(iter(model.phases))
        model.clone_phase(source_label, "CLONE_SAVE_QA")

        out = tmp_path / "cloned.iddx"
        model.save(out)
        reloaded = IddxModel.open(out)
        assert "CLONE_SAVE_QA" in reloaded.phases, (
            "Cloned phase not found after save/reload"
        )
        clone_phase = reloaded.phases["CLONE_SAVE_QA"]
        source_phase = reloaded.phases[source_label]
        assert len(clone_phase.catchments) == len(source_phase.catchments)
        assert len(clone_phase.junctions) == len(source_phase.junctions)
        assert len(clone_phase.connections) == len(source_phase.connections)


# ============================================================================
# Multi-model round-trip (for --model-dir)
# ============================================================================

class TestMultiModelRoundTrip:
    """Run round-trip on every .iddx in --model-dir."""

    def test_all_models_round_trip(self, all_model_paths, tmp_path):
        if not all_model_paths:
            pytest.skip("No models available (provide --model or --model-dir)")

        failures = []
        for i, mp in enumerate(all_model_paths):
            try:
                original = IddxModel.open(mp)
                save_path = tmp_path / f"rt_{i}.iddx"
                original.save(save_path)
                reloaded = IddxModel.open(save_path)
                for label in original.phases:
                    os = original.phases[label].summary()
                    rs = reloaded.phases[label].summary()
                    for key in ("catchments", "junctions", "drainage_systems", "connections"):
                        if os[key] != rs[key]:
                            failures.append(
                                f"{mp.name}, phase '{label}': "
                                f"{key} {os[key]} → {rs[key]}"
                            )
            except Exception as e:
                failures.append(f"{mp.name}: {type(e).__name__}: {e}")

        assert not failures, (
            f"{len(failures)} round-trip failure(s):\n" + "\n".join(failures)
        )
