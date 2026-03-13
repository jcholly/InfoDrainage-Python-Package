r"""
Example 3: Bulk-update the runoff coefficient (CV) for all catchments.

Usage:
    python 03_bulk_update_cv.py "C:\path\to\input.iddx" 0.85 "C:\path\to\output.iddx"
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel

if len(sys.argv) < 2:
    print("Usage: python 03_bulk_update_cv.py <path_to.iddx> [new_cv] [output_path]")
    sys.exit(1)

input_path = sys.argv[1]
new_cv = float(sys.argv[2]) if len(sys.argv) > 2 else 0.85
output_path = sys.argv[3] if len(sys.argv) > 3 else input_path.replace(".iddx", f"_CV{new_cv}.iddx")

model = IddxModel.open(input_path)

total_updated = 0
for label, phase in model.phases.items():
    for c in phase.catchments:
        old_cv = c.cv
        c.cv = new_cv
        total_updated += 1

model.save(output_path)

print(f"Updated {total_updated} catchments to CV={new_cv}")
print(f"Saved to: {output_path}")
