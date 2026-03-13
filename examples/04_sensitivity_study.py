r"""
Example 4: Generate a sensitivity study by varying catchment parameters.

Takes a base model and creates multiple scenario phases with different
combinations of CV, PIMP, and area scaling factors.

Usage:
    python 04_sensitivity_study.py "C:\path\to\input.iddx" "Phase Name"
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel

if len(sys.argv) < 2:
    print('Usage: python 04_sensitivity_study.py <path_to.iddx> [phase_name]')
    sys.exit(1)

input_path = sys.argv[1]
base_phase = sys.argv[2] if len(sys.argv) > 2 else "Final Layout"
output_path = input_path.replace(".iddx", "_sensitivity.iddx")

model = IddxModel.open(input_path)

if base_phase not in model.phases:
    available = list(model.phases.keys())
    print(f"Phase '{base_phase}' not found. Available: {available}")
    sys.exit(1)

for label in list(model.phases.keys()):
    if label != base_phase:
        model.remove_phase(label)

SCENARIOS = [
    {"name": "CV 0.60",        "cv": 0.60},
    {"name": "CV 0.70",        "cv": 0.70},
    {"name": "CV 0.80",        "cv": 0.80},
    {"name": "CV 0.90",        "cv": 0.90},
    {"name": "PIMP 50%",       "pimp": 50},
    {"name": "PIMP 75%",       "pimp": 75},
    {"name": "PIMP 90%",       "pimp": 90},
    {"name": "Area +50%",      "area_factor": 1.50},
    {"name": "Area -50%",      "area_factor": 0.50},
    {"name": "Worst Case",     "cv": 0.95, "pimp": 95, "area_factor": 1.25},
]

for scenario in SCENARIOS:
    name = scenario["name"]
    new_phase = model.clone_phase(base_phase, name)

    for c in new_phase.catchments:
        if "cv" in scenario:
            c.cv = scenario["cv"]
        if "pimp" in scenario:
            c.pimp = scenario["pimp"]
        if "area_factor" in scenario:
            c.area = round(c.area * scenario["area_factor"], 8)

    print(f"  Created: {name}")

model.save(output_path)
print(f"\nSaved {len(model.phases)} phases to: {output_path}")
