r"""
Example 7: Compare catchment data across all phases in a model.

Prints a side-by-side table showing how catchment properties differ
between phases -- useful for reviewing sensitivity studies or
design iterations.

Usage:
    python 07_compare_phases.py "C:\path\to\project.iddx"
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel

if len(sys.argv) < 2:
    print('Usage: python 07_compare_phases.py <path_to.iddx>')
    sys.exit(1)

path = sys.argv[1]
model = IddxModel.open(path)

phase_labels = list(model.phases.keys())
print(f"Model: {model.filepath}")
print(f"Phases: {len(phase_labels)}\n")

header = f"{'Catchment':30s}"
for label in phase_labels:
    header += f"  {label[:18]:>18s}"
print(header)
print("-" * len(header))

base_phase = model.phases[phase_labels[0]]
for base_c in base_phase.catchments:
    row_cv = f"  {'CV: ' + base_c.label:30s}"
    row_pimp = f"  {'PIMP: ' + base_c.label:30s}"
    row_area = f"  {'Area: ' + base_c.label:30s}"

    for plabel in phase_labels:
        phase = model.phases[plabel]
        match = phase.find_catchment(base_c.label)
        if match:
            row_cv += f"  {match.cv:>18.2f}"
            row_pimp += f"  {match.pimp:>17d}%"
            row_area += f"  {match.area:>18.6f}"
        else:
            row_cv += f"  {'N/A':>18s}"
            row_pimp += f"  {'N/A':>18s}"
            row_area += f"  {'N/A':>18s}"

    print(row_cv)
    print(row_pimp)
    print(row_area)
    print()

print("\nPhase summaries:")
for label, phase in model.phases.items():
    s = phase.summary()
    total_area = s["total_catchment_area_sqmi"]
    print(f"  {label:25s}  TotalArea={total_area:.6f} sqmi  "
          f"{s['catchments']}C/{s['junctions']}J/{s['connections']}P")
