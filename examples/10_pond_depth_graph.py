r"""Interactive graph of SWC Pond depth across scenarios.

Reads DemoModel4 simulation results and produces an interactive Plotly
graph showing the depth time series in the SWC pond, with a dropdown
selector for orifice size and return period combinations.

Usage:
    python examples\10_pond_depth_graph.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import IddxModel, ResultsReader, find_results
import plotly.graph_objects as go

if len(sys.argv) < 2:
    print("Usage: python 10_pond_depth_graph.py <path_to.iddx>")
    sys.exit(1)

IDDX_PATH = sys.argv[1]

POND_NODE_ID = "SWC0_SUB_1_SURF"

ORIFICE_GROUPS = [
    ("Orif-8in", "8-inch Orifice"),
    ("Orif-12in", "12-inch Orifice"),
    ("Orif-15in", "15-inch Orifice"),
]

RETURN_PERIODS = [1.0, 2.0, 5.0, 25.0, 50.0, 100.0]

COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def parse_scenario_info(scenario_name: str) -> dict:
    parts = scenario_name.split("_", 2)
    orifice_key = parts[1] if len(parts) >= 3 else ""
    runoff_label = parts[2] if len(parts) >= 3 else scenario_name
    return {"orifice": orifice_key, "runoff": runoff_label}


def main():
    print(f"Opening model: {IDDX_PATH}")
    model = IddxModel.open(IDDX_PATH)

    pond_depth = None
    for _, phase in model.phases.items():
        for ds in phase.drainage_systems:
            if ds.label.lower() == "pond":
                pond_depth = ds.depth
                break
        if pond_depth is not None:
            break

    print(f"Pond max depth: {pond_depth:.3f} ft")

    result_files = find_results(IDDX_PATH)
    if not result_files:
        print("No results found. Run analysis in InfoDrainage first.")
        return

    print(f"Loading depth time series for {len(result_files)} scenarios...")

    traces_by_key: dict[tuple[str, float], list[go.Scatter]] = {}

    for scenario_name, files in sorted(result_files.items()):
        info = parse_scenario_info(scenario_name)
        orifice_key = info["orifice"]
        runoff_label = info["runoff"]

        if not any(ok == orifice_key for ok, _ in ORIFICE_GROUPS):
            continue

        color_idx = int(runoff_label.split("-")[0][1:]) - 1 if runoff_label.startswith("R") else 0
        color = COLORS[color_idx % len(COLORS)]

        for f in files:
            parts = f.stem.rsplit("_", 2)
            if len(parts) < 3:
                continue
            try:
                rp = float(parts[-2])
            except ValueError:
                continue

            key = (orifice_key, rp)

            try:
                reader = ResultsReader(f)
                ts = reader.node_time_series(
                    POND_NODE_ID, variable="depth_above_invert", label="Pond"
                )
            except (KeyError, ValueError) as e:
                print(f"  Skipping {f.name}: {e}")
                continue

            elapsed_hours = [
                (t - ts.times[0]).total_seconds() / 3600.0 for t in ts.times
            ]

            trace = go.Scatter(
                x=elapsed_hours,
                y=ts.values,
                mode="lines",
                name=runoff_label,
                line=dict(color=color, width=1.5),
                hovertemplate=(
                    f"<b>{runoff_label}</b><br>"
                    "Time: %{x:.1f} hrs<br>"
                    "Depth: %{y:.3f} ft<br>"
                    "<extra></extra>"
                ),
                visible=False,
            )

            traces_by_key.setdefault(key, []).append(trace)

    if not traces_by_key:
        print("No pond depth data found in any results.")
        return

    print(f"  Loaded {sum(len(v) for v in traces_by_key.values())} depth traces")

    all_traces: list[go.Scatter] = []
    trace_key_map: list[tuple[str, float]] = []

    for key in sorted(traces_by_key.keys()):
        for trace in traces_by_key[key]:
            all_traces.append(trace)
            trace_key_map.append(key)

    max_x = 0.0
    for t in all_traces:
        if t.x is not None and len(t.x) > 0:
            max_x = max(max_x, max(t.x))

    if pond_depth is not None and pond_depth > 0:
        depth_line = go.Scatter(
            x=[0, max_x],
            y=[pond_depth, pond_depth],
            mode="lines",
            name=f"Max Depth ({pond_depth:.2f} ft)",
            line=dict(color="red", width=2, dash="dash"),
            hovertemplate="Max Pond Depth: %{y:.2f} ft<extra></extra>",
            visible=True,
        )
        all_traces.append(depth_line)
        trace_key_map.append(("__depth_line__", 0))

    default_key = (ORIFICE_GROUPS[0][0], 100.0)
    for i, key in enumerate(trace_key_map):
        if key == default_key:
            all_traces[i].visible = True

    buttons = []
    for orif_key, orif_display in ORIFICE_GROUPS:
        for rp in RETURN_PERIODS:
            visible_list = []
            for k in trace_key_map:
                if k == ("__depth_line__", 0):
                    visible_list.append(True)
                else:
                    visible_list.append(k == (orif_key, rp))

            buttons.append(dict(
                label=f"{orif_display}  |  {rp:.0f}-yr",
                method="update",
                args=[
                    {"visible": visible_list},
                    {"title.text": f"SWC Pond Depth &ndash; {orif_display}, {rp:.0f}-yr Storm"},
                ],
            ))

    fig = go.Figure(data=all_traces)

    default_display = ORIFICE_GROUPS[0][1]
    fig.update_layout(
        title=dict(
            text=f"SWC Pond Depth &ndash; {default_display}, 100-yr Storm",
            font=dict(size=20),
        ),
        xaxis=dict(
            title="Time (hours)",
            gridcolor="rgba(200,200,200,0.3)",
            zeroline=False,
        ),
        yaxis=dict(
            title="Depth Above Invert (ft)",
            gridcolor="rgba(200,200,200,0.3)",
            zeroline=False,
            rangemode="tozero",
        ),
        template="plotly_white",
        legend=dict(
            title="Runoff Parameters",
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="rgba(200,200,200,0.5)",
            borderwidth=1,
        ),
        hovermode="x unified",
        updatemenus=[
            dict(
                buttons=buttons,
                direction="down",
                showactive=True,
                x=0.0,
                xanchor="left",
                y=1.18,
                yanchor="top",
                bgcolor="white",
                bordercolor="rgba(100,100,100,0.4)",
                font=dict(size=12),
                pad=dict(r=10, t=5),
                active=next(
                    (i for i, b in enumerate(buttons)
                     if "100-yr" in b["label"] and default_display in b["label"]),
                    0
                ),
            ),
        ],
        annotations=[
            dict(
                text="Scenario:", x=-0.01, xref="paper", xanchor="right",
                y=1.155, yref="paper", showarrow=False, font=dict(size=13),
            ),
        ],
        margin=dict(t=120, l=70, r=30, b=60),
        autosize=True,
    )

    output_html = Path(IDDX_PATH).parent / "pond_depth_interactive.html"

    fullscreen_head = (
        '<style>'
        'html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }'
        '.js-plotly-plot, .plotly, .plot-container { width: 100% !important; height: 100% !important; }'
        '</style>'
    )

    fig.write_html(
        str(output_html),
        auto_open=True,
        full_html=True,
        include_plotlyjs=True,
        config={"responsive": True},
        post_script=[
            "window.addEventListener('resize', function(){Plotly.Plots.resize(document.querySelector('.js-plotly-plot'));});"
        ],
        default_width="100%",
        default_height="100%",
    )

    with open(output_html, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("<head>", "<head>" + fullscreen_head, 1)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nInteractive graph saved and opened:\n  {output_html}")


if __name__ == "__main__":
    main()
