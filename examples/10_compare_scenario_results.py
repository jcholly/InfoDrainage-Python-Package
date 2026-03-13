r"""
Example 10: Compare simulation results across all scenarios in a project.

Loads results from all phases (e.g. the 30 scenarios in DemoModel4),
prints a summary table, and exports CSV files for deeper analysis.

Prerequisites:
    The .iddx file must have been analyzed in InfoDrainage first.

Usage:
    python 10_compare_scenario_results.py "C:\path\to\project.iddx"
    python 10_compare_scenario_results.py   (uses DemoModel3 by default)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import (
    IddxModel,
    ScenarioComparison,
    find_results,
    load_results,
    build_label_map,
    ResultsReader,
)

if len(sys.argv) < 2:
    print("Usage: python 10_compare_scenario_results.py <path_to.iddx>")
    sys.exit(0)

iddx_path = sys.argv[1]

# ── Step 1: Check what results are available ─────────────────────────────

print("=" * 80)
print(f"Project: {iddx_path}")
print("=" * 80)

result_files = find_results(iddx_path)
if not result_files:
    print("\nNo results found. Run the analysis in InfoDrainage first.")
    sys.exit(0)

print(f"\nFound results for {len(result_files)} scenario(s):")
for phase_name, files in result_files.items():
    rps = []
    for f in files:
        parts = f.stem.rsplit("_", 2)
        if len(parts) >= 3:
            rps.append(parts[1])
    print(f"  {phase_name}: {len(files)} storms ({', '.join(rps[:6])}{'...' if len(rps) > 6 else ''} yr)")

# ── Step 2: Load model for label mapping ─────────────────────────────────

model = IddxModel.open(iddx_path)

# ── Step 3: Build cross-scenario comparison ──────────────────────────────

print("\nLoading all results for comparison...")
comp = ScenarioComparison.from_iddx(iddx_path, model=model)

# ── Step 4: Print summary table ──────────────────────────────────────────

comp.print_summary()

# ── Step 5: Export to CSV ────────────────────────────────────────────────

output_dir = os.path.dirname(iddx_path)
project_name = os.path.splitext(os.path.basename(iddx_path))[0]

summary_csv = os.path.join(output_dir, f"{project_name}_scenario_summary.csv")
comp.to_csv(summary_csv)
print(f"\nSummary CSV:  {summary_csv}")

nodes_csv = os.path.join(output_dir, f"{project_name}_node_flooding.csv")
comp.nodes_to_csv(nodes_csv, variable="peak_flooding")
print(f"Node CSV:     {nodes_csv}")

links_csv = os.path.join(output_dir, f"{project_name}_link_flows.csv")
comp.links_to_csv(links_csv, variable="peak_flow")
print(f"Link CSV:     {links_csv}")

# ── Step 6: System-level time series for one scenario ────────────────────

first_phase = list(result_files.keys())[0]
first_file = result_files[first_phase][0]
reader = ResultsReader(first_file)

print(f"\nSystem variables available: {reader.system_variables}")

if "rainfall" in reader.system_variables:
    rain_ts = reader.system_time_series("rainfall")
    print(f"  Peak rainfall intensity: {rain_ts.peak:.4f}")

if "runoff" in reader.system_variables:
    runoff_ts = reader.system_time_series("runoff")
    print(f"  Peak runoff:             {runoff_ts.peak:.4f}")

if "outfall_flow" in reader.system_variables:
    outfall_ts = reader.system_time_series("outfall_flow")
    print(f"  Peak outfall flow:       {outfall_ts.peak:.4f}")

print(f"\nDone. {len(comp.results)} scenario-storm combinations compared.")
