"""Command-line interface for iddx_core.

Usage:
    iddx summary <file.iddx>
    iddx pipes <file.iddx> [--phase PHASE] [--csv OUTPUT.csv]
    iddx compare <file.iddx> [--csv OUTPUT.csv]
    iddx validate <file.iddx> [--phase PHASE]
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

from . import __version__

logger = logging.getLogger("iddx_core")


def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.setLevel(level)
    logger.addHandler(handler)


def _load_model(filepath: str):
    """Load an IddxModel, converting errors to friendly messages."""
    from .model import IddxModel
    from .exceptions import IddxParseError

    path = Path(filepath)
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)
    if path.suffix.lower() != ".iddx":
        logger.warning("File does not have .iddx extension: %s", path)

    try:
        return IddxModel.open(path)
    except Exception as exc:
        raise IddxParseError(str(exc), filepath=str(path)) from exc


def _resolve_phase(model, phase_name: str | None):
    """Resolve a phase by name, or return the first phase if none specified."""
    if not model.phases:
        logger.error("Model has no phases.")
        sys.exit(1)

    if phase_name is None:
        return next(iter(model.phases.values()))

    phase = model.phases.get(phase_name)
    if phase is None:
        available = ", ".join(model.phases.keys())
        logger.error("Phase '%s' not found. Available: %s", phase_name, available)
        sys.exit(1)
    return phase


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_summary(args: argparse.Namespace) -> None:
    """Print a full inventory of the .iddx model."""
    model = _load_model(args.file)

    print(f"\n  InfoDrainage Model: {Path(args.file).name}")
    print(f"  Product Version:   {model.author.version}")
    print(f"  Region:            {model.units.region}")
    print(f"  Rainfall Sources:  {len(model.rainfall_sources)}")
    print(f"  Phases:            {len(model.phases)}")
    print()

    for rs in model.rainfall_sources:
        rps = ", ".join(f"{rp:.1f}" for rp in rs.return_periods)
        durs = ", ".join(f"{d:.0f}" for d in rs.durations)
        print(f"  Rainfall: {rs.label}")
        print(f"    Type:            {rs.source_type}")
        if rs.latitude or rs.longitude:
            print(f"    Location:        ({rs.latitude:.4f}, {rs.longitude:.4f})")
        print(f"    Return Periods:  {rps}")
        print(f"    Durations (min): {durs}")
        print()

    for label, phase in model.phases.items():
        s = phase.summary()
        print(f"  Phase: {label}")
        print(f"    Catchments:        {s['catchments']}")
        print(f"    Junctions:         {s['junctions']}")
        print(f"    Drainage Systems:  {s['drainage_systems']}")
        print(f"    Connections:       {s['connections']}")
        print(f"    Outfalls:          {s['outfalls']}")
        print(f"    Catchment Area:    {s['total_catchment_area_sqmi']:.6f} sq mi")
        print(f"    Total Pipe Length: {s['total_pipe_length']:.2f}")
        print()

    from .results import find_results

    result_files = find_results(args.file)
    if result_files:
        print("  SWMM Results:")
        for phase_name, files in result_files.items():
            print(f"    {phase_name}: {len(files)} result file(s)")
            for f in files:
                parts = f.stem.rsplit("_", 2)
                if len(parts) >= 3:
                    print(f"      RP={parts[1]}, Duration={parts[2]}")
        print()


def cmd_pipes(args: argparse.Namespace) -> None:
    """Export a pipe schedule."""
    from .results import _csv_safe

    model = _load_model(args.file)
    phase = _resolve_phase(model, args.phase)

    headers = [
        "Label",
        "Type",
        "From",
        "To",
        "Length",
        "Diameter_mm",
        "Diameter_in",
        "Manning_n",
        "Slope",
        "US_IL",
        "DS_IL",
        "US_CL",
        "DS_CL",
        "Barrels",
    ]

    rows = []
    for conn in phase.connections:
        rows.append(
            [
                _csv_safe(conn.label),
                conn.connection_type.name,
                _csv_safe(conn.from_junction_label),
                _csv_safe(conn.to_junction_label),
                f"{conn.length:.2f}",
                f"{conn.diameter:.1f}",
                f"{conn.diameter_inches:.2f}",
                f"{conn.mannings_n:.4f}",
                f"{conn.slope:.6f}",
                f"{conn.us_invert_level:.3f}",
                f"{conn.ds_invert_level:.3f}",
                f"{conn.us_cover_level:.3f}",
                f"{conn.ds_cover_level:.3f}",
                str(conn.num_barrels),
            ]
        )

    if args.csv:
        out_path = Path(args.csv)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)
        print(f"Pipe schedule written to {out_path} ({len(rows)} pipes)")
    else:
        widths = [
            max(len(h), max((len(r[i]) for r in rows), default=0))
            for i, h in enumerate(headers)
        ]
        header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
        print(f"\n  Pipe Schedule — Phase: {phase.label}\n")
        print(f"  {header_line}")
        print(f"  {'-' * len(header_line)}")
        for row in rows:
            print(f"  {'  '.join(v.ljust(w) for v, w in zip(row, widths))}")
        print(f"\n  {len(rows)} connections total\n")


def cmd_compare(args: argparse.Namespace) -> None:
    """Compare SWMM results across scenarios and return periods."""
    from .results import ScenarioComparison

    model = _load_model(args.file)

    comp = ScenarioComparison.from_iddx(args.file, model=model)

    if not comp.results:
        logger.error("No SWMM result files found for this project.")
        logger.error("Run analysis in InfoDrainage first to generate .out files.")
        sys.exit(1)

    if args.csv:
        out_path = Path(args.csv)
        comp.to_csv(out_path)
        print(f"Comparison written to {out_path} ({len(comp.results)} scenarios)")
    else:
        comp.print_summary()


def cmd_validate(args: argparse.Namespace) -> None:
    """Run design validation checks against the model and SWMM results."""
    model = _load_model(args.file)
    phase = _resolve_phase(model, args.phase)

    from .results import find_results, ResultsReader, build_label_map

    findings: list[tuple[str, str, str]] = []  # (severity, element, message)

    # --- Model-only checks ---

    for conn in phase.connections:
        cover_us = conn.us_cover_level - conn.us_invert_level
        cover_ds = conn.ds_cover_level - conn.ds_invert_level
        if conn.us_cover_level > 0 and conn.us_invert_level > 0:
            if cover_us < 0:
                findings.append(
                    (
                        "ERROR",
                        conn.label,
                        f"US invert ({conn.us_invert_level:.3f}) above cover ({conn.us_cover_level:.3f})",
                    )
                )
            elif cover_us < conn.diameter / 1000.0:
                findings.append(
                    (
                        "WARNING",
                        conn.label,
                        f"US cover depth ({cover_us:.3f}) less than pipe diameter",
                    )
                )
        if conn.ds_cover_level > 0 and conn.ds_invert_level > 0:
            if cover_ds < 0:
                findings.append(
                    (
                        "ERROR",
                        conn.label,
                        f"DS invert ({conn.ds_invert_level:.3f}) above cover ({conn.ds_cover_level:.3f})",
                    )
                )
            elif cover_ds < conn.diameter / 1000.0:
                findings.append(
                    (
                        "WARNING",
                        conn.label,
                        f"DS cover depth ({cover_ds:.3f}) less than pipe diameter",
                    )
                )

        if conn.length > 0 and conn.us_invert_level > 0 and conn.ds_invert_level > 0:
            grade = (conn.us_invert_level - conn.ds_invert_level) / conn.length
            if grade < 0:
                findings.append(
                    (
                        "WARNING",
                        conn.label,
                        f"Adverse slope (grade={grade:.4f}), pipe flows uphill",
                    )
                )
            elif grade == 0:
                findings.append(
                    ("WARNING", conn.label, "Zero slope — no gravitational flow")
                )

        if conn.mannings_n <= 0:
            findings.append(
                ("ERROR", conn.label, f"Invalid Manning's n ({conn.mannings_n})")
            )
        elif conn.mannings_n > 0.05:
            findings.append(
                (
                    "WARNING",
                    conn.label,
                    f"Unusually high Manning's n ({conn.mannings_n:.4f})",
                )
            )

    for j in phase.junctions:
        if j.cover_level > 0 and j.invert_level > 0:
            depth = j.cover_level - j.invert_level
            if depth <= 0:
                findings.append(
                    (
                        "ERROR",
                        j.label,
                        f"Invert ({j.invert_level:.3f}) at or above cover ({j.cover_level:.3f})",
                    )
                )

    junction_guids = {j.guid for j in phase.junctions}
    ds_guids = {ds.guid for ds in phase.drainage_systems}
    all_node_guids = junction_guids | ds_guids

    for conn in phase.connections:
        if conn.from_junction_guid and conn.from_junction_guid not in all_node_guids:
            findings.append(
                (
                    "ERROR",
                    conn.label,
                    f"FromSource GUID {conn.from_junction_guid[:8]}... references missing node",
                )
            )
        if conn.to_junction_guid and conn.to_junction_guid not in all_node_guids:
            findings.append(
                (
                    "ERROR",
                    conn.label,
                    f"ToDest GUID {conn.to_junction_guid[:8]}... references missing node",
                )
            )

    for c in phase.catchments:
        if c.to_dest_guid and c.to_dest_guid not in all_node_guids:
            findings.append(
                (
                    "WARNING",
                    c.label,
                    f"Catchment drains to GUID {c.to_dest_guid[:8]}... which is not in this phase",
                )
            )
        if c.area <= 0:
            findings.append(("WARNING", c.label, "Catchment has zero or negative area"))

    outfall_count = sum(1 for j in phase.junctions if j.is_outfall)
    outfall_count += sum(1 for ds in phase.drainage_systems if ds.is_outfall)
    if outfall_count == 0:
        findings.append(("ERROR", "Network", "No outfalls defined in this phase"))

    # --- SWMM results checks ---

    result_map = find_results(args.file)
    phase_results = result_map.get(phase.label, [])

    if phase_results:
        label_map = build_label_map(model)
        for result_path in phase_results:
            try:
                reader = ResultsReader(result_path)
            except (ValueError, FileNotFoundError) as exc:
                findings.append(
                    ("ERROR", result_path.name, f"Cannot read SWMM output: {exc}")
                )
                continue

            parts = result_path.stem.rsplit("_", 2)
            rp_label = parts[1] if len(parts) >= 3 else "?"

            for nid in reader.node_ids:
                ns = reader.node_summary(nid, label=label_map.get(nid, nid))
                if ns.peak_flooding > 0.001:
                    findings.append(
                        (
                            "WARNING",
                            ns.label,
                            f"Flooding detected: {ns.peak_flooding:.4f} (RP={rp_label})",
                        )
                    )

            for lid in reader.link_ids:
                ls = reader.link_summary(lid, label=label_map.get(lid, lid))
                if ls.max_capacity > 1.0:
                    findings.append(
                        (
                            "WARNING",
                            ls.label,
                            f"Surcharging: capacity ratio {ls.max_capacity:.2f} (RP={rp_label})",
                        )
                    )
                if 0 < ls.peak_velocity < 0.6:
                    findings.append(
                        (
                            "WARNING",
                            ls.label,
                            f"Low velocity {ls.peak_velocity:.3f} m/s — self-cleansing risk (RP={rp_label})",
                        )
                    )
                elif ls.peak_velocity > 6.0:
                    findings.append(
                        (
                            "WARNING",
                            ls.label,
                            f"High velocity {ls.peak_velocity:.3f} m/s — erosion risk (RP={rp_label})",
                        )
                    )
    else:
        findings.append(
            (
                "INFO",
                "Results",
                "No SWMM output files found — run analysis in InfoDrainage to enable results checks",
            )
        )

    # --- Output ---

    errors = [f for f in findings if f[0] == "ERROR"]
    warnings = [f for f in findings if f[0] == "WARNING"]
    infos = [f for f in findings if f[0] == "INFO"]

    print(f"\n  Validation Report — Phase: {phase.label}")
    print(f"  {'=' * 60}")
    print(f"  {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info\n")

    for severity, element, message in findings:
        marker = {"ERROR": "X", "WARNING": "!", "INFO": "-"}.get(severity, "?")
        print(f"  [{marker}] {severity:<8s} {element:<25s} {message}")

    if not findings:
        print("  All checks passed.")

    print()

    if errors:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iddx",
        description="iddx-core: CLI tools for Autodesk InfoDrainage .iddx files and SWMM results.",
    )
    parser.add_argument(
        "--version", action="version", version=f"iddx-core {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # summary
    p_summary = sub.add_parser("summary", help="Print model inventory")
    p_summary.add_argument("file", help="Path to .iddx file")

    # pipes
    p_pipes = sub.add_parser("pipes", help="Export pipe schedule")
    p_pipes.add_argument("file", help="Path to .iddx file")
    p_pipes.add_argument(
        "--phase", default=None, help="Phase name (default: first phase)"
    )
    p_pipes.add_argument(
        "--csv",
        default=None,
        metavar="OUTPUT",
        help="Write to CSV file instead of console",
    )

    # compare
    p_compare = sub.add_parser("compare", help="Compare SWMM results across scenarios")
    p_compare.add_argument("file", help="Path to .iddx file")
    p_compare.add_argument(
        "--csv",
        default=None,
        metavar="OUTPUT",
        help="Write to CSV file instead of console",
    )

    # validate
    p_validate = sub.add_parser("validate", help="Run design validation checks")
    p_validate.add_argument("file", help="Path to .iddx file")
    p_validate.add_argument(
        "--phase", default=None, help="Phase name (default: first phase)"
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=args.verbose)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "summary": cmd_summary,
        "pipes": cmd_pipes,
        "compare": cmd_compare,
        "validate": cmd_validate,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        logger.error("%s", exc)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
