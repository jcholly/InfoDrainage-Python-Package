r"""
Example 5: QA check -- find pipes with insufficient cover depth.

Compares the cover level and invert level at each end of every pipe
against a minimum required cover depth.

Usage:
    python 05_cover_depth_check.py "C:\path\to\project.iddx" 3.0
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel

if len(sys.argv) < 2:
    print("Usage: python 05_cover_depth_check.py <path_to.iddx> [min_cover_ft]")
    sys.exit(1)

input_path = sys.argv[1]
min_cover_ft = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0

model = IddxModel.open(input_path)

print(f"Cover depth check: minimum = {min_cover_ft} ft")
print(f"File: {model.filepath}\n")

failures = 0
pipes_checked = 0

for label, phase in model.phases.items():
    if not phase.connections:
        continue

    print(f"--- Phase: {label} ---")

    for p in phase.connections:
        pipes_checked += 1
        diam_ft = p.diameter / 304.8

        us_junc = phase.find_junction_by_guid(p.from_junction_guid)
        ds_junc = phase.find_junction_by_guid(p.to_junction_guid)

        us_cl = us_junc.cover_level if us_junc else 0
        ds_cl = ds_junc.cover_level if ds_junc else 0

        us_cover = us_cl - p.us_invert_level - diam_ft
        ds_cover = ds_cl - p.ds_invert_level - diam_ft

        issues = []
        if us_cover < min_cover_ft and us_cl > 0:
            issues.append(f"US cover={us_cover:.2f}ft")
        if ds_cover < min_cover_ft and ds_cl > 0:
            issues.append(f"DS cover={ds_cover:.2f}ft")

        if issues:
            failures += 1
            print(f"  FAIL: {p.label:30s}  {', '.join(issues)}")

print(f"\nChecked {pipes_checked} pipes, {failures} failures found.")
if failures == 0:
    print("All pipes meet minimum cover requirements.")
