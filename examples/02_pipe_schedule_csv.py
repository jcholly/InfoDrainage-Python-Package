r"""
Example 2: Export a pipe schedule to CSV for reports or spreadsheets.

Usage:
    python 02_pipe_schedule_csv.py "C:\path\to\project.iddx"

Produces pipe_schedule.csv in the current directory.
"""

import sys
import os
import csv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel

if len(sys.argv) < 2:
    print("Usage: python 02_pipe_schedule_csv.py <path_to.iddx>")
    sys.exit(1)

path = sys.argv[1]
model = IddxModel.open(path)

phase_label = sys.argv[2] if len(sys.argv) > 2 else list(model.phases.keys())[-1]
phase = model.phases[phase_label]

output_csv = "pipe_schedule.csv"

with open(output_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "Pipe Label",
        "From Junction",
        "To Junction",
        "Diameter (mm)",
        "Diameter (in)",
        "Length (ft)",
        "US Invert (ft)",
        "DS Invert (ft)",
        "Slope (1:X)",
        "Manning's N",
    ])

    for p in phase.connections:
        diam_in = p.diameter / 25.4
        slope = p.length / (p.us_invert_level - p.ds_invert_level) if p.us_invert_level > p.ds_invert_level else 0

        w.writerow([
            p.label,
            p.from_junction_label,
            p.to_junction_label,
            f"{p.diameter:.0f}",
            f"{diam_in:.1f}",
            f"{p.length:.2f}",
            f"{p.us_invert_level:.2f}",
            f"{p.ds_invert_level:.2f}",
            f"{slope:.2f}" if slope > 0 else "N/A",
            p.mannings_n,
        ])

print(f"Exported {len(phase.connections)} pipes from '{phase_label}' to {output_csv}")
