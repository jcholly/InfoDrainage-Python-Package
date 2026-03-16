"""Data accuracy tests for iddx_core.

Spot-checks parsed values against raw XML using ElementTree directly.
Verifies unit consistency, slope calculations, and HEC-22 config fidelity.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from pathlib import Path

from iddx_core import IddxModel
from iddx_core.enums import ALL_DSYS_TAGS, ALL_CONNECTION_TAGS


# ============================================================================
# XML spot-check helpers
# ============================================================================

def _get_xml_attr(elem, attr, default="0"):
    """Safely get an XML attribute as a string."""
    return elem.get(attr, default)


def _get_xml_float(elem, attr, default=0.0):
    val = elem.get(attr)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _get_xml_int(elem, attr, default=0):
    val = elem.get(attr)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


# ============================================================================
# Parsed-values-match-XML tests
# ============================================================================

class TestXmlSpotCheck:
    """Compare iddx_core parsed values against raw XML with ElementTree."""

    @pytest.fixture(scope="class")
    def raw_tree(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        return ET.parse(model_path)

    @pytest.fixture(scope="class")
    def model_and_xml(self, model_path, raw_tree):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        root = raw_tree.getroot()
        return model, root

    def _xml_phases(self, root):
        site = root.find("Site")
        if site is None:
            return []
        phases_container = site.find("Phases")
        if phases_container is None:
            return []
        return phases_container.findall("Phase")

    def test_catchment_areas_match_xml(self, model_and_xml):
        model, root = model_and_xml
        for xml_phase in self._xml_phases(root):
            phase_label = xml_phase.get("Label", "")
            phase = model.phases.get(phase_label)
            if phase is None:
                continue
            nodes = xml_phase.find("Nodes")
            if nodes is None:
                continue
            inflow = nodes.find("InflowNodes")
            if inflow is None:
                continue
            for ain in inflow.findall("AreaInflowNode"):
                label = ain.get("Label", "")
                xml_area = _get_xml_float(ain, "Area")
                c = phase.find_catchment(label)
                if c is None:
                    continue
                assert abs(c.area - xml_area) < 1e-9, (
                    f"Catchment '{label}': parsed area {c.area} != XML area {xml_area}"
                )

    def test_catchment_cv_matches_xml(self, model_and_xml):
        model, root = model_and_xml
        for xml_phase in self._xml_phases(root):
            phase_label = xml_phase.get("Label", "")
            phase = model.phases.get(phase_label)
            if phase is None:
                continue
            nodes = xml_phase.find("Nodes")
            if nodes is None:
                continue
            inflow = nodes.find("InflowNodes")
            if inflow is None:
                continue
            for ain in inflow.findall("AreaInflowNode"):
                label = ain.get("Label", "")
                xml_cv = _get_xml_float(ain, "CV", 0.75)
                c = phase.find_catchment(label)
                if c is None:
                    continue
                assert abs(c.cv - xml_cv) < 1e-9, (
                    f"Catchment '{label}': parsed CV {c.cv} != XML CV {xml_cv}"
                )

    def test_junction_levels_match_xml(self, model_and_xml):
        model, root = model_and_xml
        for xml_phase in self._xml_phases(root):
            phase_label = xml_phase.get("Label", "")
            phase = model.phases.get(phase_label)
            if phase is None:
                continue
            nodes = xml_phase.find("Nodes")
            if nodes is None:
                continue
            juncs = nodes.find("Junctions")
            if juncs is None:
                continue
            for jt in juncs.findall("jt"):
                label = jt.get("Label", "")
                xml_cl = _get_xml_float(jt, "CL")
                xml_il = _get_xml_float(jt, "IL")
                j = phase.find_junction(label)
                if j is None:
                    continue
                assert abs(j.cover_level - xml_cl) < 1e-6, (
                    f"Junction '{label}': CL {j.cover_level} != XML {xml_cl}"
                )
                assert abs(j.invert_level - xml_il) < 1e-6, (
                    f"Junction '{label}': IL {j.invert_level} != XML {xml_il}"
                )

    def test_connection_diameters_match_xml(self, model_and_xml):
        model, root = model_and_xml
        for xml_phase in self._xml_phases(root):
            phase_label = xml_phase.get("Label", "")
            phase = model.phases.get(phase_label)
            if phase is None:
                continue
            conexs = xml_phase.find("Conexs")
            if conexs is None:
                continue
            for tag in ALL_CONNECTION_TAGS:
                for conn_elem in conexs.findall(tag):
                    label = conn_elem.get("Label", "")
                    xml_diam = _get_xml_float(conn_elem, "Diam", 381)
                    conn = phase.find_connection(label)
                    if conn is None:
                        continue
                    assert abs(conn.diameter - xml_diam) < 0.1, (
                        f"Connection '{label}': diameter {conn.diameter} "
                        f"!= XML {xml_diam}"
                    )

    def test_connection_mannings_n_match_xml(self, model_and_xml):
        model, root = model_and_xml
        for xml_phase in self._xml_phases(root):
            phase_label = xml_phase.get("Label", "")
            phase = model.phases.get(phase_label)
            if phase is None:
                continue
            conexs = xml_phase.find("Conexs")
            if conexs is None:
                continue
            for tag in ALL_CONNECTION_TAGS:
                for conn_elem in conexs.findall(tag):
                    label = conn_elem.get("Label", "")
                    mvc = conn_elem.find("ManningsVC")
                    if mvc is None:
                        continue
                    xml_n = _get_xml_float(mvc, "ManningsN", 0.013)
                    conn = phase.find_connection(label)
                    if conn is None:
                        continue
                    assert abs(conn.mannings_n - xml_n) < 1e-6, (
                        f"Connection '{label}': Manning's n {conn.mannings_n} "
                        f"!= XML {xml_n}"
                    )


# ============================================================================
# Slope calculation accuracy
# ============================================================================

class TestSlopeCalculation:
    """Verify slope calculations match manual (US_IL - DS_IL) / length."""

    def test_slopes_match_manual_calculation(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)

        for label, phase in model.phases.items():
            for conn in phase.connections:
                if conn.length <= 0:
                    continue
                if conn.us_invert_level == 0 and conn.ds_invert_level == 0:
                    continue
                manual_grade = (
                    (conn.us_invert_level - conn.ds_invert_level) / conn.length
                )
                if abs(manual_grade) < 1e-12:
                    continue
                calc_slope = conn.calculated_slope
                expected_slope = conn.length / (conn.us_invert_level - conn.ds_invert_level)
                assert abs(calc_slope - expected_slope) < 1e-3, (
                    f"Phase '{label}', pipe '{conn.label}': "
                    f"calculated_slope={calc_slope}, "
                    f"expected 1:{expected_slope:.2f}"
                )


# ============================================================================
# Unit consistency
# ============================================================================

class TestUnitConsistency:
    """Diameters should be in mm, lengths in meters/feet, elevations consistent."""

    def test_diameters_are_in_mm(self, model_path):
        """Pipe diameters should be in mm (typically 100-3000 range)."""
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        for _, phase in model.phases.items():
            for conn in phase.connections:
                if conn.diameter <= 0:
                    continue
                assert conn.diameter >= 10, (
                    f"Pipe '{conn.label}': diameter {conn.diameter} seems too small "
                    f"for mm — possible unit error"
                )
                assert conn.diameter <= 20000, (
                    f"Pipe '{conn.label}': diameter {conn.diameter} seems too large "
                    f"for mm — possible unit error"
                )

    def test_diameter_inches_conversion(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        for _, phase in model.phases.items():
            for conn in phase.connections:
                expected_in = conn.diameter / 25.4
                assert abs(conn.diameter_inches - expected_in) < 1e-6, (
                    f"Pipe '{conn.label}': diameter_inches conversion incorrect"
                )

    def test_diameter_meters_conversion(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")
        model = IddxModel.open(model_path)
        for _, phase in model.phases.items():
            for conn in phase.connections:
                expected_m = conn.diameter / 1000.0
                assert abs(conn.diameter_meters - expected_m) < 1e-9, (
                    f"Pipe '{conn.label}': diameter_meters conversion incorrect"
                )


# ============================================================================
# HEC-22 inlet config XML fidelity
# ============================================================================

class TestHec22XmlFidelity:
    """HEC-22 inlet config fields should match raw XML HEC22InCapDet block."""

    def test_hec22_configs_match_xml(self, model_path):
        if model_path is None:
            pytest.skip("No --model provided")

        tree = ET.parse(model_path)
        root = tree.getroot()
        model = IddxModel.open(model_path)

        hec22_found = False

        site = root.find("Site")
        if site is None:
            pytest.skip("No Site element")
        phases_container = site.find("Phases")
        if phases_container is None:
            pytest.skip("No Phases element")

        for xml_phase in phases_container.findall("Phase"):
            phase_label = xml_phase.get("Label", "")
            phase = model.phases.get(phase_label)
            if phase is None:
                continue

            nodes = xml_phase.find("Nodes")
            if nodes is None:
                continue
            juncs = nodes.find("Junctions")
            if juncs is None:
                continue

            for jt in juncs.findall("jt"):
                inlet_dets = jt.find("InletDetails")
                if inlet_dets is None:
                    continue
                for idet_elem in inlet_dets.findall("IDetail"):
                    hec_cap = idet_elem.find("HEC22InCapDet")
                    if hec_cap is None:
                        continue

                    hec22_found = True
                    idet_label = idet_elem.get("Label", "Inlet")
                    xml_inlet_type = _get_xml_int(hec_cap, "HEC22InType")
                    xml_runoff = _get_xml_float(hec_cap, "Runoff")

                    junc_label = jt.get("Label", "")
                    j = phase.find_junction(junc_label)
                    if j is None:
                        continue

                    for inlet in j.inlets:
                        if inlet.label != idet_label:
                            continue
                        if inlet.hec22_config is None:
                            continue
                        cfg = inlet.hec22_config
                        assert cfg.hec22_inlet_type == xml_inlet_type, (
                            f"Junction '{junc_label}', inlet '{idet_label}': "
                            f"HEC22InType {cfg.hec22_inlet_type} != XML {xml_inlet_type}"
                        )
                        assert abs(cfg.runoff - xml_runoff) < 1e-6, (
                            f"Junction '{junc_label}', inlet '{idet_label}': "
                            f"Runoff {cfg.runoff} != XML {xml_runoff}"
                        )

                        gutter_xml = hec_cap.find("GutterDet")
                        if gutter_xml is not None and cfg.gutter is not None:
                            xml_slope = _get_xml_float(gutter_xml, "Slope")
                            assert abs(cfg.gutter.slope - xml_slope) < 1e-6, (
                                f"Gutter slope mismatch for '{junc_label}'"
                            )

        if not hec22_found:
            pytest.skip("No HEC-22 inlets found in this model")
