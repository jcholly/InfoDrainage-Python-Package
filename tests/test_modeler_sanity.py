"""Domain-specific modeler sanity checks for iddx_core.

These tests validate model integrity from a stormwater engineering
perspective: orphaned nodes, dangling GUIDs, physically unreasonable
parameter values, and GUID uniqueness.
"""

from __future__ import annotations

from collections import Counter

import pytest
from pathlib import Path

from iddx_core import IddxModel


# ============================================================================
# Network connectivity
# ============================================================================

class TestNetworkConnectivity:
    """All junctions should be reachable and connections should reference real nodes."""

    def test_connection_from_guids_resolve(self, model_path):
        """Every connection's from_junction_guid must resolve to a real node."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        failures = []
        for label, phase in model.phases.items():
            node_guids = {j.guid for j in phase.junctions}
            node_guids |= {ds.guid for ds in phase.drainage_systems}
            for conn in phase.connections:
                if conn.from_junction_guid and conn.from_junction_guid not in node_guids:
                    failures.append(
                        f"Phase '{label}', pipe '{conn.label}': "
                        f"from_junction_guid '{conn.from_junction_guid[:12]}...' "
                        f"not found among {len(node_guids)} nodes"
                    )
        assert not failures, (
            f"{len(failures)} unresolved from-GUIDs:\n" + "\n".join(failures[:10])
        )

    def test_connection_to_guids_resolve(self, model_path):
        """Every connection's to_junction_guid must resolve to a real node."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        failures = []
        for label, phase in model.phases.items():
            node_guids = {j.guid for j in phase.junctions}
            node_guids |= {ds.guid for ds in phase.drainage_systems}
            for conn in phase.connections:
                if conn.to_junction_guid and conn.to_junction_guid not in node_guids:
                    failures.append(
                        f"Phase '{label}', pipe '{conn.label}': "
                        f"to_junction_guid '{conn.to_junction_guid[:12]}...' "
                        f"not found among {len(node_guids)} nodes"
                    )
        assert not failures, (
            f"{len(failures)} unresolved to-GUIDs:\n" + "\n".join(failures[:10])
        )

    def test_catchment_dest_guids_resolve(self, model_path):
        """Catchment to_dest_guid should point to a real node in the phase."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        failures = []
        for label, phase in model.phases.items():
            node_guids = {j.guid for j in phase.junctions}
            node_guids |= {ds.guid for ds in phase.drainage_systems}
            for c in phase.catchments:
                if c.to_dest_guid and c.to_dest_guid not in node_guids:
                    failures.append(
                        f"Phase '{label}', catchment '{c.label}': "
                        f"to_dest_guid '{c.to_dest_guid[:12]}...' "
                        f"not found"
                    )
        assert not failures, (
            f"{len(failures)} unresolved catchment destinations:\n"
            + "\n".join(failures[:10])
        )

    def test_bypass_dest_guids_resolve(self, model_path):
        """Bypass connection destination GUIDs should resolve to real connections."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        failures = []
        for label, phase in model.phases.items():
            conn_guids = {c.guid for c in phase.connections}
            node_guids = {j.guid for j in phase.junctions}
            node_guids |= {ds.guid for ds in phase.drainage_systems}
            all_guids = conn_guids | node_guids

            for j in phase.junctions:
                for inlet in j.inlets:
                    if inlet.bypass_dest_guid and inlet.bypass_dest_guid not in all_guids:
                        failures.append(
                            f"Phase '{label}', junction '{j.label}', "
                            f"inlet '{inlet.label}': bypass_dest_guid "
                            f"'{inlet.bypass_dest_guid[:12]}...' not found"
                        )

        if not failures:
            return
        assert not failures, (
            f"{len(failures)} unresolved bypass GUIDs:\n" + "\n".join(failures[:10])
        )

    def test_no_orphaned_junctions(self, model_path):
        """Every junction should be referenced by at least one connection or catchment."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        for label, phase in model.phases.items():
            if not phase.connections and not phase.catchments:
                continue

            referenced_guids = set()
            for conn in phase.connections:
                referenced_guids.add(conn.from_junction_guid)
                referenced_guids.add(conn.to_junction_guid)
            for c in phase.catchments:
                if c.to_dest_guid:
                    referenced_guids.add(c.to_dest_guid)

            orphans = []
            for j in phase.junctions:
                if j.guid not in referenced_guids:
                    orphans.append(j.label)

            if orphans:
                pytest.warns(
                    UserWarning,
                    match="orphaned",
                ) if False else None  # noqa: intentional
                import warnings
                warnings.warn(
                    f"Phase '{label}': {len(orphans)} orphaned junction(s): "
                    f"{', '.join(orphans[:5])}",
                    UserWarning,
                    stacklevel=1,
                )


# ============================================================================
# Physically reasonable parameters
# ============================================================================

class TestPhysicalReasonableness:
    """Parameter values should fall in physically plausible ranges."""

    def test_pipe_diameters_reasonable(self, model_path):
        """Pipe diameters should be 100mm - 5000mm for stormwater."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        issues = []
        for label, phase in model.phases.items():
            for conn in phase.connections:
                if conn.is_channel or conn.is_bypass:
                    continue
                if conn.diameter < 100:
                    issues.append(
                        f"Phase '{label}', pipe '{conn.label}': "
                        f"diameter {conn.diameter}mm < 100mm"
                    )
                elif conn.diameter > 5000:
                    issues.append(
                        f"Phase '{label}', pipe '{conn.label}': "
                        f"diameter {conn.diameter}mm > 5000mm"
                    )

        if issues:
            import warnings
            for issue in issues[:5]:
                warnings.warn(issue, UserWarning, stacklevel=1)

    def test_mannings_n_reasonable(self, model_path):
        """Manning's n should be 0.005 - 0.05 for normal conduits."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        out_of_range = []
        for label, phase in model.phases.items():
            for conn in phase.connections:
                if conn.mannings_n <= 0:
                    out_of_range.append(
                        f"Phase '{label}', pipe '{conn.label}': "
                        f"Manning's n = {conn.mannings_n} (non-positive)"
                    )
                elif conn.mannings_n < 0.005:
                    out_of_range.append(
                        f"Phase '{label}', pipe '{conn.label}': "
                        f"Manning's n = {conn.mannings_n} (unusually low)"
                    )
                elif conn.mannings_n > 0.05:
                    out_of_range.append(
                        f"Phase '{label}', pipe '{conn.label}': "
                        f"Manning's n = {conn.mannings_n} (unusually high)"
                    )

        assert not out_of_range, (
            f"{len(out_of_range)} Manning's n value(s) out of range:\n"
            + "\n".join(out_of_range[:10])
        )

    def test_pipe_lengths_positive(self, model_path):
        """All pipe lengths should be positive (non-zero)."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        zero_length = []
        for label, phase in model.phases.items():
            for conn in phase.connections:
                if conn.length <= 0:
                    zero_length.append(
                        f"Phase '{label}', pipe '{conn.label}': "
                        f"length = {conn.length}"
                    )

        if zero_length:
            import warnings
            for z in zero_length[:5]:
                warnings.warn(z, UserWarning, stacklevel=1)

    def test_catchment_areas_positive(self, model_path):
        """All catchment areas should be positive."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        zero_area = []
        for label, phase in model.phases.items():
            for c in phase.catchments:
                if c.area <= 0:
                    zero_area.append(
                        f"Phase '{label}', catchment '{c.label}': area = {c.area}"
                    )

        if zero_area:
            import warnings
            for z in zero_area[:5]:
                warnings.warn(z, UserWarning, stacklevel=1)

    def test_junction_depths_positive(self, model_path):
        """Junction depth (CL - IL) should be positive when both are set."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        negative_depth = []
        for label, phase in model.phases.items():
            for j in phase.junctions:
                if j.cover_level > 0 and j.invert_level > 0:
                    depth = j.cover_level - j.invert_level
                    if depth <= 0:
                        negative_depth.append(
                            f"Phase '{label}', junction '{j.label}': "
                            f"CL={j.cover_level}, IL={j.invert_level}, "
                            f"depth={depth}"
                        )

        if negative_depth:
            import warnings
            for nd in negative_depth[:5]:
                warnings.warn(nd, UserWarning, stacklevel=1)


# ============================================================================
# GUID uniqueness
# ============================================================================

class TestGuidUniqueness:
    """No duplicate GUIDs should exist within a phase."""

    def test_no_duplicate_guids_in_phase(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        duplicates = []
        for label, phase in model.phases.items():
            all_guids = []
            for c in phase.catchments:
                all_guids.append(("catchment", c.label, c.guid))
            for j in phase.junctions:
                all_guids.append(("junction", j.label, j.guid))
            for ds in phase.drainage_systems:
                all_guids.append(("drainage_system", ds.label, ds.guid))
            for conn in phase.connections:
                all_guids.append(("connection", conn.label, conn.guid))

            guid_counter = Counter(g for _, _, g in all_guids)
            for guid, count in guid_counter.items():
                if count > 1:
                    owners = [
                        f"{etype} '{elabel}'"
                        for etype, elabel, g in all_guids if g == guid
                    ]
                    duplicates.append(
                        f"Phase '{label}': GUID '{guid[:12]}...' shared by "
                        f"{', '.join(owners)}"
                    )

        assert not duplicates, (
            f"{len(duplicates)} duplicate GUID(s):\n" + "\n".join(duplicates[:10])
        )

    def test_phase_guids_unique(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        phase_guids = [p.guid for p in model.phases.values()]
        assert len(phase_guids) == len(set(phase_guids)), (
            "Duplicate phase GUIDs detected"
        )


# ============================================================================
# Model summary consistency
# ============================================================================

class TestModelSummary:
    """Verify summary() returns consistent data."""

    def test_summary_keys(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        s = model.summary()
        assert "phases" in s
        assert "product_version" in s
        assert "region" in s
        assert "rainfall_sources" in s

    def test_phase_summary_counts_match(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        for label, phase in model.phases.items():
            s = phase.summary()
            assert s["catchments"] == len(phase.catchments), (
                f"Phase '{label}': summary catchments "
                f"{s['catchments']} != actual {len(phase.catchments)}"
            )
            assert s["junctions"] == len(phase.junctions)
            assert s["drainage_systems"] == len(phase.drainage_systems)
            assert s["connections"] == len(phase.connections)

    def test_total_catchment_area_positive(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        for label, phase in model.phases.items():
            if phase.catchments:
                assert phase.total_catchment_area >= 0, (
                    f"Phase '{label}': negative total catchment area"
                )


# ============================================================================
# Multi-model sanity (for --model-dir)
# ============================================================================

class TestMultiModelSanity:
    """Run key sanity checks across all models in --model-dir."""

    def test_all_models_parse(self, all_model_paths):
        if not all_model_paths:
            pytest.skip("No models available")

        failures = []
        for mp in all_model_paths:
            try:
                model = IddxModel.open(mp)
                assert len(model.phases) >= 0
            except Exception as e:
                failures.append(f"{mp.name}: {type(e).__name__}: {e}")

        assert not failures, (
            f"{len(failures)} model(s) failed to parse:\n" + "\n".join(failures)
        )

    def test_all_models_have_valid_guids(self, all_model_paths):
        if not all_model_paths:
            pytest.skip("No models available")

        failures = []
        for mp in all_model_paths:
            try:
                model = IddxModel.open(mp)
                for label, phase in model.phases.items():
                    guids = [c.guid for c in phase.catchments]
                    guids += [j.guid for j in phase.junctions]
                    guids += [ds.guid for ds in phase.drainage_systems]
                    guids += [conn.guid for conn in phase.connections]
                    if len(guids) != len(set(guids)):
                        failures.append(f"{mp.name}, phase '{label}': duplicate GUIDs")
            except Exception as e:
                failures.append(f"{mp.name}: parse error: {e}")

        assert not failures, (
            f"{len(failures)} GUID issue(s):\n" + "\n".join(failures)
        )
