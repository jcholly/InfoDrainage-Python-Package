r"""
Example 9: Create DemoModel4 with 30 scenario combinations.

Clones the "Final Layout" phase from DemoModel3 and creates 30 scenarios
by combining 3 orifice sizes with 10 different runoff parameter sets.

    3 orifice sizes  x  10 runoff sets  =  30 scenarios

Usage:
    python 09_demo4_scenarios.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel

if len(sys.argv) < 3:
    print("Usage: python 09_demo4_scenarios.py <source.iddx> <output.iddx> [phase_name]")
    sys.exit(1)

SOURCE = sys.argv[1]
OUTPUT = sys.argv[2]
BASE_PHASE = sys.argv[3] if len(sys.argv) > 3 else "Final Layout"

ORIFICE_SIZES = [
    {"label": "Orif-8in",  "diameter_m": 0.2032},
    {"label": "Orif-12in", "diameter_m": 0.3048},
    {"label": "Orif-15in", "diameter_m": 0.3810},
]

RUNOFF_PARAMS = [
    {"label": "R01-CV40-P50",  "cv": 0.40, "pimp": 50},
    {"label": "R02-CV45-P60",  "cv": 0.45, "pimp": 60},
    {"label": "R03-CV50-P70",  "cv": 0.50, "pimp": 70},
    {"label": "R04-CV55-P75",  "cv": 0.55, "pimp": 75},
    {"label": "R05-CV60-P80",  "cv": 0.60, "pimp": 80},
    {"label": "R06-CV65-P85",  "cv": 0.65, "pimp": 85},
    {"label": "R07-CV70-P90",  "cv": 0.70, "pimp": 90},
    {"label": "R08-CV75-P95",  "cv": 0.75, "pimp": 95},
    {"label": "R09-CV85-P98",  "cv": 0.85, "pimp": 98},
    {"label": "R10-CV95-P100", "cv": 0.95, "pimp": 100},
]

# ── Load source model ────────────────────────────────────────────────────

model = IddxModel.open(SOURCE)

if BASE_PHASE not in model.phases:
    available = list(model.phases.keys())
    print(f"Phase '{BASE_PHASE}' not found. Available: {available}")
    sys.exit(1)

for label in list(model.phases.keys()):
    if label != BASE_PHASE:
        model.remove_phase(label)

# ── Generate 30 scenarios ────────────────────────────────────────────────

scenario_num = 0

for orifice in ORIFICE_SIZES:
    for runoff in RUNOFF_PARAMS:
        scenario_num += 1
        name = f"S{scenario_num:02d}_{orifice['label']}_{runoff['label']}"

        new_phase = model.clone_phase(BASE_PHASE, name)

        for ds in new_phase.drainage_systems:
            for outlet in ds.outlets:
                if outlet.orifice_diameter > 0:
                    outlet.orifice_diameter = orifice["diameter_m"]

        for c in new_phase.catchments:
            c.cv = runoff["cv"]
            c.pimp = runoff["pimp"]

        print(f"  [{scenario_num:2d}/30]  {name}")

model.remove_phase(BASE_PHASE)

# ── Save ──────────────────────────────────────────────────────────────────

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
model.save(OUTPUT)

print(f"\nDemoModel4 saved with {len(model.phases)} scenarios to:\n  {OUTPUT}")
