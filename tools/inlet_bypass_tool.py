"""
Inlet & Bypass Connection Tool for InfoDrainage
================================================
Standalone automation tool that uses iddx_core to inspect, audit,
edit, and auto-generate HEC-22 inlet configurations and bypass
connections in .iddx project files.

Usage:
    python tools/inlet_bypass_tool.py report  model.iddx
    python tools/inlet_bypass_tool.py audit   model.iddx
    python tools/inlet_bypass_tool.py edit    model.iddx -o updated.iddx [options]
    python tools/inlet_bypass_tool.py auto-bypass model.iddx -o updated.iddx
    python tools/inlet_bypass_tool.py export  model.iddx --csv inlets.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import (
    IddxModel, Phase, Junction, DrainageSystem, Connection,
    InletDetail, Hec22InletConfig, GutterDetail,
    GrateInletParams, CurbInletParams, ComboInletParams, SlottedInletParams,
    CrossSectionDetails, CrossSectionPoint,
    ConnectionType,
)
from iddx_core.utils import new_guid


# -- Data structures ------------------------------------------------------

HEC22_TYPE_NAMES = {0: "Grate", 1: "Curb", 2: "Combo", 3: "Slotted"}
ICAP_TYPE_NAMES = {0: "None", 1: "Low/High Flow", 2: "Rated by Flow", 3: "HEC-22"}
LOCATION_NAMES = {0: "On-Grade", 1: "In-Sag"}


@dataclass
class InletNode:
    """Wrapper tying an InletDetail to its parent junction/dsys."""
    node_label: str
    node_guid: str
    node_x: float
    node_y: float
    node_cover_level: float
    node_invert_level: float
    inlet: InletDetail
    node_type: str = "Junction"


@dataclass
class BypassChainLink:
    """One hop in a bypass chain: inlet -> connection -> next inlet."""
    from_node: str
    from_inlet_guid: str
    connection_label: str
    connection_guid: str
    to_node: str


@dataclass
class BypassChain:
    """A complete chain of bypass connections from first inlet to terminal."""
    links: list[BypassChainLink] = field(default_factory=list)

    @property
    def start_node(self) -> str:
        return self.links[0].from_node if self.links else ""

    @property
    def end_node(self) -> str:
        return self.links[-1].to_node if self.links else ""

    @property
    def length(self) -> int:
        return len(self.links)

    def node_labels(self) -> list[str]:
        labels = [self.links[0].from_node] if self.links else []
        for link in self.links:
            labels.append(link.to_node)
        return labels


# -- Helpers --------------------------------------------------------------

def _resolve_phase(model: IddxModel, phase_name: Optional[str] = None) -> Phase:
    if phase_name:
        for p in model.phases.values():
            if p.label == phase_name:
                return p
        raise SystemExit(f"Phase '{phase_name}' not found. "
                         f"Available: {[p.label for p in model.phases.values()]}")
    return next(iter(model.phases.values()))


def _collect_inlet_nodes(phase: Phase) -> list[InletNode]:
    """Gather all inlets with their parent node info."""
    nodes = []
    for jn in phase.junctions:
        for inlet in jn.inlets:
            nodes.append(InletNode(
                node_label=jn.label, node_guid=jn.guid,
                node_x=jn.x, node_y=jn.y,
                node_cover_level=jn.cover_level,
                node_invert_level=jn.invert_level,
                inlet=inlet, node_type="Junction",
            ))
    for ds in phase.drainage_systems:
        for inlet in ds.inlets:
            nodes.append(InletNode(
                node_label=ds.label, node_guid=ds.guid,
                node_x=ds.x, node_y=ds.y,
                node_cover_level=ds.cover_level,
                node_invert_level=ds.invert_level,
                inlet=inlet, node_type="DrainageSystem",
            ))
    return nodes


def _build_guid_label_map(phase: Phase) -> dict[str, str]:
    m = {}
    for jn in phase.junctions:
        m[jn.guid] = jn.label
    for ds in phase.drainage_systems:
        m[ds.guid] = ds.label
    return m


def _build_bypass_connections(phase: Phase) -> list[Connection]:
    return [c for c in phase.connections if c.is_bypass]


def _trace_bypass_chains(phase: Phase) -> list[BypassChain]:
    """Trace all bypass chains from start to terminal."""
    bypass_conns = _build_bypass_connections(phase)
    guid_label = _build_guid_label_map(phase)

    from_guid_to_conn: dict[str, Connection] = {}
    for bc in bypass_conns:
        from_guid_to_conn[bc.from_junction_guid] = bc

    inlet_nodes = _collect_inlet_nodes(phase)
    inlets_by_bypass_guid: dict[str, InletNode] = {}
    for inode in inlet_nodes:
        if inode.inlet.bypass_dest_guid:
            inlets_by_bypass_guid[inode.node_guid] = inode

    start_guids = set()
    all_dest_guids = {bc.to_junction_guid for bc in bypass_conns}
    for inode in inlets_by_bypass_guid.values():
        if inode.node_guid not in all_dest_guids:
            start_guids.add(inode.node_guid)

    if not start_guids:
        for inode in inlets_by_bypass_guid.values():
            start_guids.add(inode.node_guid)

    chains = []
    visited_starts = set()
    for start_guid in start_guids:
        if start_guid in visited_starts:
            continue
        chain = BypassChain()
        current_guid = start_guid
        seen = set()
        while current_guid in from_guid_to_conn and current_guid not in seen:
            seen.add(current_guid)
            conn = from_guid_to_conn[current_guid]
            chain.links.append(BypassChainLink(
                from_node=guid_label.get(conn.from_junction_guid, conn.from_junction_label),
                from_inlet_guid=current_guid,
                connection_label=conn.label,
                connection_guid=conn.guid,
                to_node=guid_label.get(conn.to_junction_guid, conn.to_junction_label),
            ))
            current_guid = conn.to_junction_guid
        if chain.links:
            chains.append(chain)
            visited_starts.add(start_guid)
    return chains


def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def _format_hec22_detail(inlet: InletDetail) -> str:
    """Format HEC-22 config as a concise string."""
    cfg = inlet.hec22_config
    if cfg is None:
        return "No HEC-22 config"

    itype = HEC22_TYPE_NAMES.get(cfg.hec22_inlet_type, "?")
    parts = [itype]

    if cfg.gutter:
        g = cfg.gutter
        parts.append(f"Slope=1:{g.slope:.1f} W={g.width:.4f}m n={g.mannings_n}")

    p = cfg.inlet_params
    if p:
        loc = LOCATION_NAMES.get(getattr(p, "location", 0), "?")
        parts.append(f"Loc={loc}")
        if hasattr(p, "grate_length"):
            parts.append(f"GrateL={p.grate_length:.4f}")
        if hasattr(p, "width"):
            parts.append(f"W={p.width:.4f}")
        if hasattr(p, "curb_length"):
            parts.append(f"CurbL={p.curb_length:.4f}")
        if hasattr(p, "depression"):
            parts.append(f"Dep={p.depression:.1f}mm")
        if hasattr(p, "clogging") and p.clogging > 0:
            parts.append(f"Clog={p.clogging:.0f}%")

    return " | ".join(parts)


# -- Commands -------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> None:
    """Full inlet and bypass connection inventory."""
    model = IddxModel.open(args.model)
    phase = _resolve_phase(model, args.phase)
    inlet_nodes = _collect_inlet_nodes(phase)
    bypass_conns = _build_bypass_connections(phase)
    chains = _trace_bypass_chains(phase)

    print("=" * 80)
    print(f"INLET & BYPASS REPORT -- {os.path.basename(args.model)}")
    print(f"Phase: {phase.label}")
    print("=" * 80)

    hec22_inlets = [n for n in inlet_nodes if n.inlet.hec22_config is not None]
    non_hec22 = [n for n in inlet_nodes if n.inlet.hec22_config is None]

    print(f"\nTotal inlets: {len(inlet_nodes)}")
    print(f"  HEC-22 configured: {len(hec22_inlets)}")
    print(f"  Non-HEC-22: {len(non_hec22)}")
    print(f"Bypass connections: {len(bypass_conns)}")
    print(f"Bypass chains: {len(chains)}")

    # HEC-22 inlets detail
    print(f"\n{'-' * 80}")
    print("HEC-22 INLET DETAILS")
    print(f"{'-' * 80}")
    for inode in sorted(hec22_inlets, key=lambda n: n.node_label):
        inlet = inode.inlet
        bypass = ""
        if inlet.bypass_dest_label:
            bypass = f"  -> bypass to {inlet.bypass_dest_label}"
        src_labels = ", ".join(s.label for s in inlet.sources) if inlet.sources else "none"
        print(f"\n  {inode.node_label} [{inlet.label}]")
        print(f"    Cap Type: {ICAP_TYPE_NAMES.get(inlet.capacity_type, '?')}")
        print(f"    Config:   {_format_hec22_detail(inlet)}")
        print(f"    Sources:  {src_labels}")
        if bypass:
            print(f"    Bypass:   -> {inlet.bypass_dest_label}")
        if inlet.hec22_results and inlet.hec22_results.captured_flow > 0:
            r = inlet.hec22_results
            print(f"    Results:  Approach={r.approach_flow:.4f} "
                  f"Captured={r.captured_flow:.4f} "
                  f"Bypass={r.bypass_flow:.4f} "
                  f"Eff={r.efficiency:.1%}")

    # Bypass connections detail
    if bypass_conns:
        print(f"\n{'-' * 80}")
        print("BYPASS CONNECTIONS")
        print(f"{'-' * 80}")
        for bc in sorted(bypass_conns, key=lambda c: c.label):
            xs = ""
            if bc.cross_section:
                xs = f"  XS: {len(bc.cross_section.points)} pts"
            print(f"  {bc.label}: {bc.from_junction_label} -> {bc.to_junction_label} "
                  f"L={bc.length:.1f}m H={bc.conduit_height:.1f}mm{xs}")

    # Bypass chains
    if chains:
        print(f"\n{'-' * 80}")
        print("BYPASS CHAINS (flow path tracing)")
        print(f"{'-' * 80}")
        for i, chain in enumerate(chains, 1):
            labels = chain.node_labels()
            print(f"\n  Chain {i} ({chain.length} hops):")
            print(f"    {' -> '.join(labels)}")

    # Inlets without bypass
    no_bypass = [n for n in hec22_inlets if not n.inlet.bypass_dest_guid]
    if no_bypass:
        print(f"\n{'-' * 80}")
        print("TERMINAL INLETS (no bypass connection)")
        print(f"{'-' * 80}")
        for inode in sorted(no_bypass, key=lambda n: n.node_label):
            print(f"  {inode.node_label} [{inode.inlet.label}]")


def cmd_audit(args: argparse.Namespace) -> None:
    """Check for inlet/bypass configuration issues."""
    model = IddxModel.open(args.model)
    phase = _resolve_phase(model, args.phase)
    inlet_nodes = _collect_inlet_nodes(phase)
    bypass_conns = _build_bypass_connections(phase)
    guid_label = _build_guid_label_map(phase)

    errors = []
    warnings = []

    # Check 1: HEC-22 inlets without full config
    for inode in inlet_nodes:
        inlet = inode.inlet
        if inlet.capacity_type == 3 and inlet.hec22_config is None:
            errors.append(f"[MISSING CONFIG] {inode.node_label} [{inlet.label}]: "
                          f"ICapType=HEC-22 but no HEC22InCapDet block")
        if inlet.hec22_config is not None and inlet.hec22_config.gutter is None:
            warnings.append(f"[NO GUTTER] {inode.node_label} [{inlet.label}]: "
                            f"HEC-22 config present but no gutter details")

    # Check 2: Bypass destination points to non-existent connection
    conn_guids = {c.guid for c in phase.connections}
    for inode in inlet_nodes:
        inlet = inode.inlet
        if inlet.bypass_dest_guid and inlet.bypass_dest_guid not in conn_guids:
            errors.append(f"[BROKEN BYPASS] {inode.node_label} [{inlet.label}]: "
                          f"bypass GUID {inlet.bypass_dest_guid[:8]}... "
                          f"not found in connections")

    # Check 3: Inlet has bypass dest but no CustomCon exists for it
    bypass_from_guids = {bc.from_junction_guid for bc in bypass_conns}
    for inode in inlet_nodes:
        inlet = inode.inlet
        if inlet.bypass_dest_guid and inode.node_guid not in bypass_from_guids:
            warnings.append(f"[NO CONN] {inode.node_label} [{inlet.label}]: "
                            f"has bypass dest '{inlet.bypass_dest_label}' but no "
                            f"CustomCon originates from this node")

    # Check 4: CustomCon exists but no inlet points to it
    bypass_to_guids = {bc.to_junction_guid for bc in bypass_conns}
    inlet_bypass_dests = set()
    for inode in inlet_nodes:
        if inode.inlet.bypass_dest_guid:
            inlet_bypass_dests.add(inode.inlet.bypass_dest_guid)

    # Check 5: Clogging factor checks
    for inode in inlet_nodes:
        cfg = inode.inlet.hec22_config
        if cfg and cfg.inlet_params:
            p = cfg.inlet_params
            if hasattr(p, "clogging") and p.clogging >= 100:
                errors.append(f"[100% CLOG] {inode.node_label} [{inode.inlet.label}]: "
                              f"clogging = {p.clogging}% -- inlet fully blocked")
            elif hasattr(p, "clogging") and p.clogging > 50:
                warnings.append(f"[HIGH CLOG] {inode.node_label} [{inode.inlet.label}]: "
                                f"clogging = {p.clogging}%")

    # Check 6: Zero gutter width
    for inode in inlet_nodes:
        cfg = inode.inlet.hec22_config
        if cfg and cfg.gutter and cfg.gutter.width <= 0:
            errors.append(f"[ZERO GUTTER] {inode.node_label} [{inode.inlet.label}]: "
                          f"gutter width = 0")

    # Check 7: Duplicate bypass connections from same node
    from_counts: dict[str, list[str]] = {}
    for bc in bypass_conns:
        from_counts.setdefault(bc.from_junction_guid, []).append(bc.label)
    for guid, labels in from_counts.items():
        if len(labels) > 1:
            node_label = guid_label.get(guid, guid[:8])
            warnings.append(f"[DUP BYPASS] {node_label}: "
                            f"{len(labels)} bypass connections originate here: "
                            f"{', '.join(labels)}")

    # Output
    print("=" * 80)
    print(f"INLET AUDIT -- {os.path.basename(args.model)}")
    print(f"Phase: {phase.label}")
    print("=" * 80)

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  X {e}")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")

    if not errors and not warnings:
        print("\n  All inlet/bypass checks passed.")

    total = len(inlet_nodes)
    hec22 = sum(1 for n in inlet_nodes if n.inlet.hec22_config is not None)
    with_bypass = sum(1 for n in inlet_nodes if n.inlet.bypass_dest_guid)
    print(f"\nSummary: {total} inlets ({hec22} HEC-22), "
          f"{with_bypass} with bypass, {len(bypass_conns)} bypass connections")
    print(f"         {len(errors)} errors, {len(warnings)} warnings")

    if errors:
        raise SystemExit(1)


def cmd_edit(args: argparse.Namespace) -> None:
    """Bulk-edit HEC-22 inlet properties."""
    model = IddxModel.open(args.model)
    phase = _resolve_phase(model, args.phase)
    inlet_nodes = _collect_inlet_nodes(phase)
    hec22_inlets = [n for n in inlet_nodes if n.inlet.hec22_config is not None]

    if not hec22_inlets:
        print("No HEC-22 inlets found.")
        return

    changes = 0

    if args.clogging is not None:
        for inode in hec22_inlets:
            p = inode.inlet.hec22_config.inlet_params
            if p and hasattr(p, "clogging"):
                old = p.clogging
                p.clogging = args.clogging
                if old != args.clogging:
                    changes += 1
                    print(f"  {inode.node_label}: clogging {old:.0f}% -> {args.clogging:.0f}%")

    if args.gutter_n is not None:
        for inode in hec22_inlets:
            g = inode.inlet.hec22_config.gutter
            if g:
                old = g.mannings_n
                g.mannings_n = args.gutter_n
                if old != args.gutter_n:
                    changes += 1
                    print(f"  {inode.node_label}: gutter n {old} -> {args.gutter_n}")

    if args.gutter_width is not None:
        for inode in hec22_inlets:
            g = inode.inlet.hec22_config.gutter
            if g:
                old = g.width
                g.width = args.gutter_width
                if old != args.gutter_width:
                    changes += 1
                    print(f"  {inode.node_label}: gutter width {old:.4f} -> {args.gutter_width:.4f}")

    if args.depression is not None:
        for inode in hec22_inlets:
            p = inode.inlet.hec22_config.inlet_params
            if p and hasattr(p, "depression"):
                old = p.depression
                p.depression = args.depression
                if old != args.depression:
                    changes += 1
                    print(f"  {inode.node_label}: depression {old:.1f} -> {args.depression:.1f}mm")

    if args.grate_type is not None:
        for inode in hec22_inlets:
            p = inode.inlet.hec22_config.inlet_params
            if p and hasattr(p, "grate_type_swmm5"):
                old = p.grate_type_swmm5
                p.grate_type_swmm5 = args.grate_type
                if old != args.grate_type:
                    changes += 1
                    print(f"  {inode.node_label}: grate type {old} -> {args.grate_type}")

    if changes == 0:
        print("No changes applied.")
        return

    out = args.output or args.model
    model.save(out)
    print(f"\n{changes} edits applied. Saved to {out}")


def cmd_auto_bypass(args: argparse.Namespace) -> None:
    """Automatically create bypass connections between inlets."""
    model = IddxModel.open(args.model)
    phase = _resolve_phase(model, args.phase)
    inlet_nodes = _collect_inlet_nodes(phase)
    bypass_conns = _build_bypass_connections(phase)
    guid_label = _build_guid_label_map(phase)

    hec22_inlets = [n for n in inlet_nodes if n.inlet.hec22_config is not None]
    if not hec22_inlets:
        print("No HEC-22 inlets to process.")
        return

    # Find nodes that already have a bypass connection leaving them
    already_connected_from = {bc.from_junction_guid for bc in bypass_conns}

    # Find inlets needing bypass (have HEC-22 but no bypass dest set and
    # no existing bypass connection from their node)
    needs_bypass = [n for n in hec22_inlets
                    if not n.inlet.bypass_dest_guid
                    and n.node_guid not in already_connected_from]

    if not needs_bypass:
        print("All HEC-22 inlets already have bypass connections.")
        return

    # Determine candidate targets: all junctions/dsys that receive pipe connections
    pipe_connections = [c for c in phase.connections if not c.is_bypass]

    ds_node_map: dict[str, object] = {}
    for jn in phase.junctions:
        ds_node_map[jn.guid] = jn
    for ds in phase.drainage_systems:
        ds_node_map[ds.guid] = ds

    max_dist = args.max_distance if args.max_distance else 200.0
    created = 0
    next_idx = len(phase.connections)
    targeted_guids: set[str] = set()

    print("=" * 80)
    print(f"AUTO-BYPASS -- {os.path.basename(args.model)}")
    print(f"Phase: {phase.label}")
    print(f"Max search distance: {max_dist:.0f}m")
    print("=" * 80)

    for inode in needs_bypass:
        # Find the downstream junction (where this inlet's outlet goes)
        ds_junction_guid = ""
        parent = ds_node_map.get(inode.node_guid)
        if parent and hasattr(parent, "outlets"):
            for outlet in parent.outlets:
                if outlet.to_dest_guid:
                    ds_junction_guid = outlet.to_dest_guid
                    break

        # Find nearest HEC-22 inlet that is NOT on the same node
        # and is NOT already this node's downstream junction
        best_target = None
        best_dist = float("inf")

        for candidate in hec22_inlets:
            if candidate.node_guid == inode.node_guid:
                continue
            if candidate.node_guid == ds_junction_guid:
                continue
            if candidate.node_guid in targeted_guids:
                continue

            d = _distance(inode.node_x, inode.node_y,
                          candidate.node_x, candidate.node_y)
            if d < best_dist and d <= max_dist:
                best_dist = d
                best_target = candidate

        if best_target is None:
            if not args.quiet:
                print(f"  SKIP {inode.node_label}: no suitable target within {max_dist:.0f}m")
            continue

        if args.dry_run:
            created += 1
            targeted_guids.add(inode.node_guid)
            print(f"  WOULD CREATE: {inode.node_label} -> {best_target.node_label} "
                  f"(dist={best_dist:.1f}m)")
            continue

        # Create bypass connection
        bypass_label = f"Auto Bypass ({created + 1})"
        bypass_conn = Connection(
            index=next_idx,
            label=bypass_label,
            guid=new_guid(),
            connection_type=ConnectionType.CUSTOM_BYPASS,
            length=best_dist,
            us_cover_level=inode.node_cover_level,
            us_invert_level=inode.node_cover_level - 0.1524,
            ds_cover_level=best_target.node_cover_level,
            ds_invert_level=best_target.node_cover_level - 0.1524,
            slope=best_dist / max(0.001, abs(
                (inode.node_cover_level - 0.1524) -
                (best_target.node_cover_level - 0.1524)
            )) if abs((inode.node_cover_level - 0.1524) -
                      (best_target.node_cover_level - 0.1524)) > 0.001 else 0.0,
            diameter=508.254,
            conduit_height=152.4,
            conduit_height_user=True,
            num_barrels=1,
            entry_loss=0.5,
            mannings_n=0.013,
            part_family=-1,
            from_junction_guid=inode.node_guid,
            from_junction_label=inode.node_label,
            to_junction_guid=best_target.node_guid,
            to_junction_label=best_target.node_label,
            cross_section=CrossSectionDetails(
                con_covered=False, diameter=0.0,
                points=[
                    CrossSectionPoint(0, 12.7),
                    CrossSectionPoint(406.4, 4.064),
                    CrossSectionPoint(508, 0),
                    CrossSectionPoint(508.254, 12.7),
                ],
            ),
            _element_tag="CustomCon",
        )
        phase.add_connection(bypass_conn)

        # Wire up the inlet's bypass destination (points to the connection GUID)
        inode.inlet.bypass_dest_guid = bypass_conn.guid
        inode.inlet.bypass_dest_label = bypass_label
        targeted_guids.add(inode.node_guid)

        next_idx += 1
        created += 1
        print(f"  CREATED: {inode.node_label} -> {best_target.node_label} "
              f"[{bypass_label}] dist={best_dist:.1f}m")

    if args.dry_run:
        print(f"\nDry run: {created} bypass connections would be created.")
        return

    if created > 0:
        out = args.output or args.model
        model.save(out)
        print(f"\n{created} bypass connections created. Saved to {out}")
    else:
        print("\nNo bypass connections created.")


def cmd_export(args: argparse.Namespace) -> None:
    """Export inlet schedule to CSV."""
    model = IddxModel.open(args.model)
    phase = _resolve_phase(model, args.phase)
    inlet_nodes = _collect_inlet_nodes(phase)
    bypass_conns = _build_bypass_connections(phase)

    rows = []
    for inode in sorted(inlet_nodes, key=lambda n: n.node_label):
        inlet = inode.inlet
        cfg = inlet.hec22_config

        row = {
            "Node Label": inode.node_label,
            "Node Type": inode.node_type,
            "Inlet Label": inlet.label,
            "Capacity Type": ICAP_TYPE_NAMES.get(inlet.capacity_type, str(inlet.capacity_type)),
            "HEC-22 Inlet Type": HEC22_TYPE_NAMES.get(cfg.hec22_inlet_type, "") if cfg else "",
            "Location": "",
            "Gutter Slope (1:X)": "",
            "Gutter Width (m)": "",
            "Gutter Manning n": "",
            "Road Cross Slope (1:X)": "",
            "Gutter Cross Slope (1:X)": "",
            "Grate Length (m)": "",
            "Grate Width (m)": "",
            "Grate Type (SWMM5)": "",
            "Curb Length (m)": "",
            "Curb Height (m)": "",
            "Throat Angle": "",
            "Depression (mm)": "",
            "Clogging (%)": "",
            "Bypass Dest": inlet.bypass_dest_label,
            "Approach Flow": "",
            "Captured Flow": "",
            "Bypass Flow": "",
            "Efficiency": "",
            "Source Catchments": ", ".join(s.label for s in inlet.sources),
        }

        if cfg and cfg.gutter:
            g = cfg.gutter
            row["Gutter Slope (1:X)"] = f"{g.slope:.2f}"
            row["Gutter Width (m)"] = f"{g.width:.4f}"
            row["Gutter Manning n"] = f"{g.mannings_n}"
            row["Road Cross Slope (1:X)"] = f"{g.road_x_slope:.2f}"
            row["Gutter Cross Slope (1:X)"] = f"{g.gutter_x_slope:.2f}"

        if cfg and cfg.inlet_params:
            p = cfg.inlet_params
            row["Location"] = LOCATION_NAMES.get(getattr(p, "location", 0), "")
            if hasattr(p, "grate_length"):
                row["Grate Length (m)"] = f"{p.grate_length:.6f}"
            if hasattr(p, "width"):
                row["Grate Width (m)"] = f"{p.width:.6f}"
            if hasattr(p, "grate_type_swmm5"):
                row["Grate Type (SWMM5)"] = str(p.grate_type_swmm5)
            if hasattr(p, "curb_length"):
                row["Curb Length (m)"] = f"{p.curb_length:.6f}"
            if hasattr(p, "height"):
                row["Curb Height (m)"] = f"{p.height:.4f}"
            if hasattr(p, "throat_angle"):
                row["Throat Angle"] = str(p.throat_angle)
            if hasattr(p, "depression"):
                row["Depression (mm)"] = f"{p.depression:.1f}"
            if hasattr(p, "clogging"):
                row["Clogging (%)"] = f"{p.clogging:.1f}"

        if inlet.hec22_results:
            r = inlet.hec22_results
            row["Approach Flow"] = f"{r.approach_flow:.6f}"
            row["Captured Flow"] = f"{r.captured_flow:.6f}"
            row["Bypass Flow"] = f"{r.bypass_flow:.6f}"
            row["Efficiency"] = f"{r.efficiency:.2%}" if r.approach_flow > 0 else ""

        rows.append(row)

    # Bypass connection rows
    bypass_rows = []
    for bc in sorted(bypass_conns, key=lambda c: c.label):
        bypass_rows.append({
            "Connection Label": bc.label,
            "From Node": bc.from_junction_label,
            "To Node": bc.to_junction_label,
            "Length (m)": f"{bc.length:.2f}",
            "Conduit Height (mm)": f"{bc.conduit_height:.1f}",
            "Diameter (mm)": f"{bc.diameter:.3f}",
            "Cross Section Points": len(bc.cross_section.points) if bc.cross_section else 0,
        })

    csv_path = args.csv
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            if bypass_rows:
                f.write("\n")
                writer2 = csv.DictWriter(f, fieldnames=bypass_rows[0].keys())
                writer2.writeheader()
                writer2.writerows(bypass_rows)
        print(f"Exported {len(rows)} inlets and {len(bypass_rows)} bypass connections to {csv_path}")
    else:
        # Print to console
        print(f"{'Node':<15} {'Inlet':<15} {'Type':<8} {'Gutter Slope':<14} "
              f"{'Width':<10} {'Depression':<12} {'Clog%':<8} {'Bypass To':<20}")
        print("-" * 102)
        for row in rows:
            print(f"{row['Node Label']:<15} {row['Inlet Label']:<15} "
                  f"{row['HEC-22 Inlet Type']:<8} "
                  f"{row['Gutter Slope (1:X)']:<14} "
                  f"{row['Grate Width (m)']:<10} "
                  f"{row['Depression (mm)']:<12} "
                  f"{row['Clogging (%)']:<8} "
                  f"{row['Bypass Dest']:<20}")

        if bypass_rows:
            print(f"\n{'Connection':<25} {'From':<15} {'To':<15} {'Length (m)':<12} {'Height (mm)':<12}")
            print("-" * 79)
            for br in bypass_rows:
                print(f"{br['Connection Label']:<25} {br['From Node']:<15} "
                      f"{br['To Node']:<15} {br['Length (m)']:<12} "
                      f"{br['Conduit Height (mm)']:<12}")


# -- CLI ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inlet_bypass_tool",
        description="Inlet & Bypass Connection Tool for InfoDrainage .iddx files",
    )
    parser.add_argument("--version", action="version", version="1.0.0")
    sub = parser.add_subparsers(dest="command", required=True)

    # report
    p_report = sub.add_parser("report", help="Full inlet and bypass inventory")
    p_report.add_argument("model", help="Path to .iddx file")
    p_report.add_argument("--phase", help="Phase label (default: first phase)")

    # audit
    p_audit = sub.add_parser("audit", help="Check for inlet/bypass issues")
    p_audit.add_argument("model", help="Path to .iddx file")
    p_audit.add_argument("--phase", help="Phase label (default: first phase)")

    # edit
    p_edit = sub.add_parser("edit", help="Bulk-edit HEC-22 inlet properties")
    p_edit.add_argument("model", help="Path to .iddx file")
    p_edit.add_argument("-o", "--output", help="Output file (default: overwrite input)")
    p_edit.add_argument("--phase", help="Phase label (default: first phase)")
    p_edit.add_argument("--clogging", type=float, help="Set clogging factor (%%)")
    p_edit.add_argument("--gutter-n", type=float, help="Set gutter Manning's n")
    p_edit.add_argument("--gutter-width", type=float, help="Set gutter width (m)")
    p_edit.add_argument("--depression", type=float, help="Set local depression (mm)")
    p_edit.add_argument("--grate-type", type=int,
                        help="Set SWMM5 grate type (0-7)")

    # auto-bypass
    p_auto = sub.add_parser("auto-bypass",
                            help="Auto-create bypass connections between inlets")
    p_auto.add_argument("model", help="Path to .iddx file")
    p_auto.add_argument("-o", "--output", help="Output file (default: overwrite input)")
    p_auto.add_argument("--phase", help="Phase label (default: first phase)")
    p_auto.add_argument("--max-distance", type=float, default=200.0,
                        help="Max distance (m) to search for bypass target (default: 200)")
    p_auto.add_argument("--dry-run", action="store_true",
                        help="Preview changes without saving")
    p_auto.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress skip messages")

    # export
    p_export = sub.add_parser("export", help="Export inlet schedule")
    p_export.add_argument("model", help="Path to .iddx file")
    p_export.add_argument("--phase", help="Phase label (default: first phase)")
    p_export.add_argument("--csv", help="Export to CSV file (default: print to console)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "report": cmd_report,
        "audit": cmd_audit,
        "edit": cmd_edit,
        "auto-bypass": cmd_auto_bypass,
        "export": cmd_export,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
