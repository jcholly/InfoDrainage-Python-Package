r"""
Test suite: Open, parse, round-trip save, and re-read every .iddx in the
InfoDrainage Model Library.  Verifies that:

  1. Every file opens without error
  2. All phases, catchments, junctions, drainage systems, and connections parse
  3. Editing fields on each element type survives a save/reload round-trip
  4. Results files (if present) can be loaded and queried
  5. ScenarioComparison works on models with results

Usage:
    python test_model_library.py
"""

import sys
import os
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from iddx_core import (
    IddxModel, ScenarioComparison, ResultsReader,
    find_results, build_label_map,
)

if len(sys.argv) < 2:
    print("Usage: python test_model_library.py <path_to_model_library_folder>")
    sys.exit(1)

LIB_DIR = Path(sys.argv[1])

PASS = 0
FAIL = 0
WARNINGS = []


def log_pass(msg):
    global PASS
    PASS += 1
    print(f"    PASS  {msg}")


def log_fail(msg, exc=None):
    global FAIL
    FAIL += 1
    detail = f" -- {exc}" if exc else ""
    print(f"    FAIL  {msg}{detail}")


def test_open_and_summary(filepath: Path):
    """Test 1: Open and print summary."""
    model = IddxModel.open(filepath)
    n_phases = len(model.phases)
    n_rain = len(model.rainfall_sources)
    log_pass(f"Opened: {n_phases} phases, {n_rain} rainfall sources")

    for label, phase in model.phases.items():
        s = phase.summary()
        log_pass(
            f"Phase '{label}': "
            f"{s['catchments']}C {s['junctions']}J "
            f"{s['drainage_systems']}DS {s['connections']}P "
            f"{s['outfalls']}OF"
        )
    return model


def test_element_access(model: IddxModel):
    """Test 2: Access and inspect all parsed elements."""
    for label, phase in model.phases.items():
        for c in phase.catchments:
            assert c.label, f"Catchment missing label in {label}"
            assert c.guid, f"Catchment missing GUID in {label}"
            _ = c.area, c.cv, c.pimp, c.runoff_method

        for j in phase.junctions:
            assert j.label, f"Junction missing label in {label}"
            _ = j.cover_level, j.invert_level, j.depth
            for o in j.outlets:
                _ = o.outlet_type, o.il, o.orifice_diameter, o.weir_width

        for ds in phase.drainage_systems:
            assert ds.label, f"DrainageSystem missing label in {label}"
            _ = ds.system_type, ds.depth, ds.invert_level, ds.top_area
            for o in ds.outlets:
                _ = o.outlet_type, o.orifice_diameter, o.weir_width

        for p in phase.connections:
            assert p.label, f"Connection missing label in {label}"
            _ = p.diameter, p.length, p.mannings_n, p.entry_loss

    log_pass("All elements accessible without error")


def test_round_trip(model: IddxModel, filepath: Path):
    """Test 3: Save to temp, re-open, and verify key counts match."""
    with tempfile.NamedTemporaryFile(suffix=".iddx", delete=False, dir=tempfile.gettempdir()) as tmp:
        tmp_path = tmp.name

    try:
        model.save(tmp_path)
        model2 = IddxModel.open(tmp_path)

        for label in model.phases:
            if label not in model2.phases:
                log_fail(f"Phase '{label}' missing after round-trip")
                continue

            p1 = model.phases[label]
            p2 = model2.phases[label]

            if len(p1.catchments) != len(p2.catchments):
                log_fail(f"'{label}' catchment count: {len(p1.catchments)} -> {len(p2.catchments)}")
            if len(p1.junctions) != len(p2.junctions):
                log_fail(f"'{label}' junction count: {len(p1.junctions)} -> {len(p2.junctions)}")
            if len(p1.drainage_systems) != len(p2.drainage_systems):
                log_fail(f"'{label}' DS count: {len(p1.drainage_systems)} -> {len(p2.drainage_systems)}")
            if len(p1.connections) != len(p2.connections):
                log_fail(f"'{label}' connection count: {len(p1.connections)} -> {len(p2.connections)}")

        log_pass("Round-trip save/reload -- element counts match")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def test_edit_round_trip(model: IddxModel):
    """Test 4: Edit fields on each element type and verify they survive save/reload."""
    with tempfile.NamedTemporaryFile(suffix=".iddx", delete=False, dir=tempfile.gettempdir()) as tmp:
        tmp_path = tmp.name

    try:
        first_phase = list(model.phases.values())[0]

        edits = {}

        if first_phase.catchments:
            c = first_phase.catchments[0]
            c.cv = 0.1234
            c.pimp = 42
            c.cv_winter = 0.99
            edits["catchment"] = (c.label, {"cv": 0.1234, "pimp": 42, "cv_winter": 0.99})
            if c.toc_details:
                c.toc_details.tc = 999.0
                c.toc_details.runoff_coefficient = 0.33
                edits["toc"] = True
            if c.scs_details:
                c.scs_details.pervious_cn = 55
                c.scs_details.pimp = 33
                edits["scs"] = True

        if first_phase.junctions:
            j = first_phase.junctions[0]
            j.sump_depth = 0.321
            j.sealed = True
            j.bend_loss = 0.77
            edits["junction"] = (j.label, {"sump_depth": 0.321, "sealed": True, "bend_loss": 0.77})

        if first_phase.connections:
            p = first_phase.connections[0]
            p.entry_loss = 0.88
            p.exit_loss = 0.44
            p.num_barrels = 3
            edits["connection"] = (p.label, {"entry_loss": 0.88, "exit_loss": 0.44, "num_barrels": 3})

        if first_phase.drainage_systems:
            ds = first_phase.drainage_systems[0]
            ds.freeboard = 999.0
            edits["drainage_system"] = (ds.label, {"freeboard": 999.0})
            for o in ds.outlets:
                if o.orifice_diameter > 0:
                    o.orifice_diameter = 0.5555
                    edits["orifice"] = True
                    break

        model.save(tmp_path)
        m2 = IddxModel.open(tmp_path)
        p2 = list(m2.phases.values())[0]

        ok = True
        if "catchment" in edits:
            c2 = p2.catchments[0]
            if abs(c2.cv - 0.1234) > 1e-6:
                log_fail(f"Catchment CV not saved: {c2.cv}")
                ok = False
            if c2.pimp != 42:
                log_fail(f"Catchment PIMP not saved: {c2.pimp}")
                ok = False
            if abs(c2.cv_winter - 0.99) > 1e-6:
                log_fail(f"Catchment CV_Winter not saved: {c2.cv_winter}")
                ok = False
            if "toc" in edits and c2.toc_details:
                if abs(c2.toc_details.tc - 999.0) > 1e-3:
                    log_fail(f"ToC TC not saved: {c2.toc_details.tc}")
                    ok = False
                if abs(c2.toc_details.runoff_coefficient - 0.33) > 1e-6:
                    log_fail(f"ToC RunoffCoeff not saved: {c2.toc_details.runoff_coefficient}")
                    ok = False
            if "scs" in edits and c2.scs_details:
                if c2.scs_details.pervious_cn != 55:
                    log_fail(f"SCS CN not saved: {c2.scs_details.pervious_cn}")
                    ok = False

        if "junction" in edits:
            j2 = p2.junctions[0]
            if abs(j2.sump_depth - 0.321) > 1e-6:
                log_fail(f"Junction sump not saved: {j2.sump_depth}")
                ok = False
            if not j2.sealed:
                log_fail("Junction sealed not saved")
                ok = False
            if abs(j2.bend_loss - 0.77) > 1e-6:
                log_fail(f"Junction bend_loss not saved: {j2.bend_loss}")
                ok = False

        if "connection" in edits:
            p2c = p2.connections[0]
            if abs(p2c.entry_loss - 0.88) > 1e-6:
                log_fail(f"Connection entry_loss not saved: {p2c.entry_loss}")
                ok = False
            if abs(p2c.exit_loss - 0.44) > 1e-6:
                log_fail(f"Connection exit_loss not saved: {p2c.exit_loss}")
                ok = False
            if p2c.num_barrels != 3:
                log_fail(f"Connection num_barrels not saved: {p2c.num_barrels}")
                ok = False

        if "drainage_system" in edits:
            ds2 = p2.drainage_systems[0]
            if abs(ds2.freeboard - 999.0) > 1e-3:
                log_fail(f"DS freeboard not saved: {ds2.freeboard}")
                ok = False
            if "orifice" in edits:
                for o2 in ds2.outlets:
                    if o2.orifice_diameter > 0:
                        if abs(o2.orifice_diameter - 0.5555) > 1e-6:
                            log_fail(f"Orifice diameter not saved: {o2.orifice_diameter}")
                            ok = False
                        break

        if ok:
            log_pass("Edit round-trip -- all modified values preserved")

    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def test_results(filepath: Path):
    """Test 5: Load results if available."""
    result_files = find_results(filepath)
    if not result_files:
        WARNINGS.append(f"  No results for {filepath.parent.name}")
        return

    total = sum(len(v) for v in result_files.values())
    loaded = 0
    for phase_name, paths in result_files.items():
        for p in paths:
            try:
                reader = ResultsReader(p)
                _ = reader.node_ids, reader.link_ids, reader.system_variables
                loaded += 1
            except Exception as e:
                log_fail(f"Results file {p.name}", e)

    log_pass(f"Results: loaded {loaded}/{total} .out files across {len(result_files)} phases")

    try:
        comp = ScenarioComparison.from_iddx(filepath)
        table = comp.summary_table()
        log_pass(f"ScenarioComparison: {len(table)} rows")
    except Exception as e:
        log_fail("ScenarioComparison", e)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    global PASS, FAIL

    iddx_files = sorted(LIB_DIR.rglob("*.iddx"))
    print(f"Testing {len(iddx_files)} models from InfoDrainage Model Library\n")

    for filepath in iddx_files:
        rel = filepath.relative_to(LIB_DIR)
        print(f"\n{'=' * 70}")
        print(f"  {rel}")
        print(f"{'=' * 70}")

        try:
            model = test_open_and_summary(filepath)
        except Exception as e:
            log_fail(f"OPEN FAILED", e)
            traceback.print_exc()
            continue

        try:
            test_element_access(model)
        except Exception as e:
            log_fail(f"ELEMENT ACCESS FAILED", e)
            traceback.print_exc()

        try:
            model_fresh = IddxModel.open(filepath)
            test_round_trip(model_fresh, filepath)
        except Exception as e:
            log_fail(f"ROUND-TRIP FAILED", e)
            traceback.print_exc()

        try:
            model_fresh2 = IddxModel.open(filepath)
            test_edit_round_trip(model_fresh2)
        except Exception as e:
            log_fail(f"EDIT ROUND-TRIP FAILED", e)
            traceback.print_exc()

        try:
            test_results(filepath)
        except Exception as e:
            log_fail(f"RESULTS FAILED", e)
            traceback.print_exc()

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  RESULTS:  {PASS} passed,  {FAIL} failed")
    print(f"{'=' * 70}")

    if WARNINGS:
        print(f"\nWarnings ({len(WARNINGS)}):")
        for w in WARNINGS:
            print(w)

    if FAIL > 0:
        print(f"\n{FAIL} FAILURES detected.")
        sys.exit(1)
    else:
        print("\nAll tests passed.")


if __name__ == "__main__":
    main()
