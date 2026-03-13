r"""
Example 1: Print a complete summary of any .iddx project.

Usage:
    python 01_model_summary.py "C:\path\to\project.iddx"
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel

if len(sys.argv) < 2:
    print("Usage: python 01_model_summary.py <path_to.iddx>")
    sys.exit(1)

path = sys.argv[1]
model = IddxModel.open(path)

print(f"File:    {model.filepath}")
print(f"Product: {model.author.product} {model.author.version}")
print(f"User:    {model.author.user}")
print(f"Region:  {model.units.region}")
print(f"Phases:  {len(model.phases)}")

if model.rainfall_sources:
    print(f"\nRainfall Sources ({len(model.rainfall_sources)}):")
    for rs in model.rainfall_sources:
        print(f"  {rs.label} ({rs.source_type})")
        print(f"    Location: ({rs.latitude:.4f}, {rs.longitude:.4f})")
        print(f"    Return periods: {rs.return_periods}")

for label, phase in model.phases.items():
    s = phase.summary()
    print(f"\n{'=' * 60}")
    print(f"Phase: {label}")
    print(f"{'=' * 60}")
    print(f"  Catchments:       {s['catchments']}")
    print(f"  Junctions:        {s['junctions']}")
    print(f"  Drainage Systems: {s['drainage_systems']}")
    print(f"  Pipes/Channels:   {s['connections']}")
    print(f"  Outfalls:         {s['outfalls']}")
    print(f"  Total Area:       {s['total_catchment_area_sqmi']:.4f} sq mi")
    print(f"  Total Pipe Len:   {s['total_pipe_length']:.1f}")

    if phase.catchments:
        print(f"\n  Catchments:")
        for c in phase.catchments:
            print(f"    {c.label:30s}  Area={c.area:.6f}  CV={c.cv}  PIMP={c.pimp}%  Method={c.runoff_method.name}")

    if phase.drainage_systems:
        print(f"\n  Stormwater Controls:")
        for ds in phase.drainage_systems:
            print(f"    {ds.label:30s}  Type={ds.system_type.name}  Depth={ds.depth:.2f}")
            for o in ds.outlets:
                print(f"      Outlet: {o.label} ({o.outlet_type.name})")

    if phase.junctions:
        print(f"\n  Junctions:")
        for j in phase.junctions:
            out = " [OUTFALL]" if j.is_outfall else ""
            print(f"    {j.label:30s}  CL={j.cover_level:.2f}  IL={j.invert_level:.2f}{out}")

    if phase.connections:
        print(f"\n  Connections:")
        for p in phase.connections:
            print(f"    {p.label:30s}  D={p.diameter:.0f}mm  L={p.length:.1f}  N={p.mannings_n}")
