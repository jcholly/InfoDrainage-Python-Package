# InfoDrainage Python Package (`iddx_core`)

A pure-Python toolkit for programmatically reading, writing, and manipulating Autodesk InfoDrainage `.iddx` project files. No external dependencies required.

## Installation

### Option 1: Clone from GitHub

```bash
git clone https://github.com/jcholly/InfoDrainage-Python-Package.git
cd InfoDrainage-Python-Package
```

Then use it directly — no `pip install` needed. Just run scripts from inside this folder, or add the folder to your Python path.

### Option 2: Copy into an existing project

Copy the `iddx_core/` folder into your project directory. That's the entire package — 8 Python files, zero dependencies.

### Requirements

- **Python 3.10+**
- No `pip install` needed — the package uses only Python's built-in `xml.etree.ElementTree` and `struct`

### Verify it works

```bash
python -c "from iddx_core import IddxModel; print('iddx_core is ready')"
```

---

## Quick Start

### 1. Open a model and print a summary

```python
from iddx_core import IddxModel

model = IddxModel.open(r"C:\path\to\project.iddx")

for label, phase in model.phases.items():
    s = phase.summary()
    print(f"{label}: {s['catchments']} catchments, {s['junctions']} junctions, {s['connections']} pipes")
```

### 2. Change all catchment runoff coefficients and save

```python
from iddx_core import IddxModel

model = IddxModel.open(r"C:\path\to\project.iddx")
phase = model.phases["Proposed"]

for catchment in phase.catchments:
    catchment.cv = 0.85

model.save(r"C:\path\to\updated.iddx")
```

Open `updated.iddx` in InfoDrainage — every catchment now shows CV = 0.85.

### 3. Create scenario variations

```python
from iddx_core import IddxModel

model = IddxModel.open(r"C:\path\to\project.iddx")

for pimp in [40, 60, 80, 95]:
    new_phase = model.clone_phase("Proposed", f"PIMP {pimp}%")
    for c in new_phase.catchments:
        c.pimp = pimp

model.save(r"C:\path\to\scenarios.iddx")
```

This creates 4 new phases, each with a different percent impervious. Open in InfoDrainage and run all scenarios at once.

---

## Example Scripts

The `examples/` folder contains 8 ready-to-run scripts. Each one accepts a file path as an argument, or uses a built-in default.

| Script | What it does |
|--------|-------------|
| `01_model_summary.py` | Print a full inventory of any `.iddx` file |
| `02_pipe_schedule_csv.py` | Export a pipe schedule to CSV |
| `03_bulk_update_cv.py` | Change the runoff coefficient on every catchment |
| `04_sensitivity_study.py` | Generate 10 scenario phases varying CV, PIMP, and area |
| `05_cover_depth_check.py` | QA check: flag pipes with less than X feet of cover |
| `06_create_model.py` | Build a complete model from scratch |
| `07_compare_phases.py` | Side-by-side comparison of catchment data across phases |
| `08_read_results.py` | Read simulation results: peak flows, depths, flooding |

**Run an example:**

```bash
cd InfoDrainage-Python-Package
python examples/01_model_summary.py "C:\path\to\project.iddx"
```

---

## What can you do with this?

| Use case | How |
|----------|-----|
| **Batch modify catchments** | Loop over `phase.catchments`, change `.cv`, `.pimp`, `.area`, save |
| **Generate sensitivity studies** | `model.clone_phase()` with different parameters per scenario |
| **Export pipe schedules** | Loop over `phase.connections`, write to CSV |
| **QA checks** | Compare cover levels vs invert levels to check pipe cover depth |
| **Build models programmatically** | `IddxModel.new()` + add catchments, junctions, pipes from data |
| **Compare design iterations** | Read multiple `.iddx` files and compare element counts/properties |
| **Read simulation results** | `ResultsReader` parses .out files for peak flows, depths, flooding |
| **Compare storms** | `load_results()` to compare peak flows across return periods |

---

## API Reference

### Core Classes

| Class | Description |
|-------|-------------|
| `IddxModel` | Top-level model. `IddxModel.open()` to read, `.save()` to write, `.new()` to create from scratch. |
| `Phase` | A design scenario containing all network elements. Access via `model.phases["name"]`. |
| `Catchment` | Inflow area. Key properties: `.label`, `.area`, `.cv`, `.pimp`, `.runoff_method` |
| `Junction` | Manhole, inlet, or outfall. Key properties: `.label`, `.cover_level`, `.invert_level`, `.is_outfall` |
| `DrainageSystem` | Stormwater control (pond, tank, swale, etc.). Key properties: `.label`, `.system_type`, `.depth` |
| `Connection` | Pipe or channel. Key properties: `.label`, `.diameter`, `.length`, `.mannings_n` |
| `RainfallSource` | Rainfall data (NOAA, FEH, etc.). Key properties: `.label`, `.return_periods` |
| `ResultsReader` | Read simulation results from `.out` files. Key methods: `.node_summary()`, `.link_summary()`, `.node_time_series()`, `.link_time_series()` |

### Key Enumerations

| Enum | Values |
|------|--------|
| `RunoffMethod` | `RATIONAL`, `SCS_CURVE_NUMBER`, `SWMM`, `STATIC`, `FOUL`, and others |
| `DrainageSystemType` | `POND`, `SWALE`, `BIORETENTION`, `POROUS_PAVEMENT`, `CHAMBER`, `TANK` |
| `ConnectionType` | `CIRCULAR_PIPE`, `BOX_CULVERT`, `TRAPEZOIDAL_CHANNEL`, `TRIANGULAR_CHANNEL` |
| `OutletType` | `FLOW_CONTROL`, `ORIFICE`, `WEIR`, `COMPLEX`, `PUMP`, `FREE_OUTLET` |

### Common Operations

```python
from iddx_core import IddxModel, Catchment, Junction, Connection

# Open
model = IddxModel.open("project.iddx")

# Access phases
phase = model.phases["Proposed"]
print(phase.summary())

# Find elements by label
j = phase.find_junction("MH-1")
c = phase.find_catchment("Site-A")

# Modify
c.cv = 0.90
c.pimp = 80

# Clone a phase
new_phase = model.clone_phase("Proposed", "High Density")

# Add new elements
phase.add_junction(Junction(label="MH-NEW", x=100, y=200, cover_level=250, invert_level=247))

# Access rainfall
for rs in model.rainfall_sources:
    storm = rs.get_storm(100.0)  # 100-year storm
    if storm:
        print(f"100-yr depth: {storm.total_depth:.2f}")

# Save
model.save("updated.iddx")
```

### Reading Simulation Results

After running analysis in InfoDrainage, results are saved as `.out` binary files (SWMM format) in a subfolder next to the `.iddx` file.

```python
from iddx_core import IddxModel, ResultsReader, find_results, load_results, build_label_map

# Find all result files for a project
result_files = find_results(r"C:\path\to\project.iddx")
for phase, files in result_files.items():
    print(f"{phase}: {len(files)} storms analyzed")

# Load a single result file
results = ResultsReader(r"C:\path\to\project\Proposed_100.000_1440.00.out")
print(f"Nodes: {len(results.node_ids)}, Links: {len(results.link_ids)}")
print(f"Periods: {results.num_periods}, Interval: {results.report_interval_seconds}s")

# Get peak results for all links (cross-reference with model for labels)
model = IddxModel.open(r"C:\path\to\project.iddx")
label_map = build_label_map(model)

for ls in results.all_link_summaries(label_map):
    if ls.peak_flow > 0.001:
        print(f"{ls.label}: peak flow = {ls.peak_flow:.4f}")

# Get a full time series
ts = results.link_time_series(results.link_ids[0], variable="flow_rate")
print(f"Peak flow: {ts.peak:.4f} at {ts.peak_time}")

# Compare peak flows across return periods
all_results = load_results(r"C:\path\to\project.iddx")
for rp, r in sorted(all_results["Proposed"].items()):
    ls = r.link_summary(results.link_ids[0])
    print(f"{rp:.0f}-yr: {ls.peak_flow:.4f}")
```

---

## Package Structure

```
InfoDrainage-Python-Package/
├── README.md                    ← This file
├── iddx_core/                   ← The Python package (copy this folder to use)
│   ├── __init__.py
│   ├── model.py                 ← IddxModel (open/save/create)
│   ├── phase.py                 ← Phase (scenario container)
│   ├── nodes.py                 ← Catchment, Junction, DrainageSystem
│   ├── connections.py           ← Connection (pipes, channels)
│   ├── rainfall.py              ← RainfallSource, StormEvent
│   ├── results.py               ← ResultsReader (read .out binary files)
│   ├── enums.py                 ← RunoffMethod, OutletType, etc.
│   └── utils.py                 ← XML helpers, GUID generation
└── examples/                    ← Ready-to-run example scripts
```
