"""
Example 6: Create a simple stormwater model from scratch.

Builds a small network: 3 catchments, 4 junctions (1 outfall), 3 pipes,
then saves it as a valid .iddx file you can open in InfoDrainage.

Usage:
    python 06_create_model.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel, Catchment, Junction, Connection, RunoffMethod

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "example_new_model.iddx")

model = IddxModel.new(user="", region="United States")
phase = model.create_phase("Proposed")

mh1 = Junction(label="MH-1", x=1000, y=2000, cover_level=250.0, invert_level=246.0)
mh2 = Junction(label="MH-2", x=1050, y=2000, cover_level=249.5, invert_level=245.5)
mh3 = Junction(label="MH-3", x=1100, y=2000, cover_level=249.0, invert_level=245.0)
of1 = Junction(label="OF-1", x=1150, y=2000, cover_level=248.0, invert_level=244.0, is_outfall=True)

for j in [mh1, mh2, mh3, of1]:
    phase.add_junction(j)

c1 = Catchment(label="Parking Lot A", x=1000, y=2020, cv=0.90, area=0.002, pimp=95)
c2 = Catchment(label="Rooftop B", x=1050, y=2020, cv=0.95, area=0.001, pimp=100)
c3 = Catchment(label="Lawn C", x=1100, y=2020, cv=0.35, area=0.003, pimp=15)

c1.to_dest_guid = mh1.guid
c1.to_dest_label = mh1.label
c2.to_dest_guid = mh2.guid
c2.to_dest_label = mh2.label
c3.to_dest_guid = mh3.guid
c3.to_dest_label = mh3.label

for c in [c1, c2, c3]:
    phase.add_catchment(c)

pipes = [
    ("P-1", 381, mh1, mh2),
    ("P-2", 457, mh2, mh3),
    ("P-3", 610, mh3, of1),
]

for plabel, diameter, from_j, to_j in pipes:
    pipe = Connection(
        label=plabel,
        diameter=float(diameter),
        length=50.0,
        mannings_n=0.013,
        us_invert_level=from_j.invert_level,
        ds_invert_level=to_j.invert_level,
        from_junction_guid=from_j.guid,
        from_junction_label=from_j.label,
        to_junction_guid=to_j.guid,
        to_junction_label=to_j.label,
    )
    phase.add_connection(pipe)

model.save(OUTPUT)

print(f"Created new model: {OUTPUT}")
print(f"  Junctions:  {len(phase.junctions)} ({sum(1 for j in phase.junctions if j.is_outfall)} outfall)")
print(f"  Catchments: {len(phase.catchments)}")
print(f"  Pipes:      {len(phase.connections)}")
print(f"\nOpen this file in InfoDrainage to verify.")
