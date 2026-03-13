r"""Read simulation results from InfoDrainage .out files.

Usage:
    python examples\08_read_results.py "C:\path\to\project.iddx"

The .iddx file must have been analyzed in InfoDrainage first, which
creates a results subfolder containing .out binary files.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel, ResultsReader, find_results, load_results, build_label_map


def main():
    if len(sys.argv) < 2:
        print("Usage: python 08_read_results.py <path_to.iddx>")
        return
    iddx_path = sys.argv[1]

    # Step 1: Find result files
    print("=" * 70)
    print(f"Project: {iddx_path}")
    print("=" * 70)

    result_files = find_results(iddx_path)
    if not result_files:
        print("No results found. Run analysis in InfoDrainage first.")
        return

    print(f"\nFound results for {len(result_files)} phases:")
    for phase_name, files in result_files.items():
        rps = []
        for f in files:
            parts = f.stem.rsplit("_", 2)
            if len(parts) >= 3:
                rps.append(parts[1])
        print(f"  {phase_name}: {len(files)} storms ({', '.join(rps[:6])}{'...' if len(rps) > 6 else ''} yr)")

    # Step 2: Open the model to get human-readable labels
    model = IddxModel.open(iddx_path)
    label_map = build_label_map(model)

    # Step 3: Load results for the first phase, highest return period
    first_phase = list(result_files.keys())[0]
    last_file = result_files[first_phase][-1]
    print(f"\n{'=' * 70}")
    print(f"Loading: {last_file.name}")
    print("=" * 70)

    results = ResultsReader(last_file)
    print(f"  Flow units: {results.flow_units}")
    print(f"  Periods: {results.num_periods}")
    print(f"  Interval: {results.report_interval_seconds}s ({results.report_interval_seconds // 60} min)")
    print(f"  Time span: {results.start_time} to {results.end_time}")
    print(f"  Nodes: {len(results.node_ids)}")
    print(f"  Links: {len(results.link_ids)}")

    # Step 4: Print node summaries
    print(f"\n--- Node Peak Results ---")
    print(f"{'Label':<20s} {'Peak Head':>12s} {'Peak Inflow':>14s} {'Flooding':>12s}")
    print("-" * 60)

    node_summaries = results.all_node_summaries(label_map)
    for ns in node_summaries:
        if ns.peak_total_inflow > 0.0001:
            print(
                f"{ns.label:<20s} "
                f"{ns.peak_head:>12.3f} "
                f"{ns.peak_total_inflow:>14.6f} "
                f"{ns.peak_flooding:>12.6f}"
            )

    # Step 5: Print link summaries
    print(f"\n--- Link Peak Results ---")
    print(f"{'Label':<20s} {'Peak Flow':>12s} {'Peak Depth':>12s} {'Peak Vel':>12s} {'Capacity':>10s}")
    print("-" * 68)

    link_summaries = results.all_link_summaries(label_map)
    for ls in link_summaries:
        if abs(ls.peak_flow) > 0.0001:
            print(
                f"{ls.label:<20s} "
                f"{ls.peak_flow:>12.6f} "
                f"{ls.peak_depth:>12.4f} "
                f"{ls.peak_velocity:>12.4f} "
                f"{ls.max_capacity:>10.4f}"
            )

    # Step 6: Compare peak flows across all return periods for the first phase
    print(f"\n--- Peak Flows by Return Period ({first_phase}) ---")
    all_results = load_results(iddx_path, model)
    phase_results = all_results.get(first_phase, {})

    if phase_results and results.link_ids:
        first_link = results.link_ids[0]
        link_label = label_map.get(first_link, first_link)
        print(f"Link: {link_label}")
        print(f"{'Return Period':>15s} {'Peak Flow':>14s}")
        print("-" * 30)
        for rp in sorted(phase_results.keys()):
            r = phase_results[rp]
            try:
                ls = r.link_summary(first_link, label=link_label)
                print(f"{rp:>12.1f} yr {ls.peak_flow:>14.6f}")
            except KeyError:
                pass


if __name__ == "__main__":
    main()
