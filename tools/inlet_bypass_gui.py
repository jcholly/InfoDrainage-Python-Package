"""
Inlet & Bypass Tool - GUI
==========================
Tkinter-based graphical interface for inspecting, sizing, editing, and
automating HEC-22 inlet configurations and bypass connections in
InfoDrainage .iddx project files.

Usage:
    python tools/inlet_bypass_gui.py
"""

from __future__ import annotations

import csv
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iddx_core import (
    IddxModel, Phase, InletDetail,
    ConnectionType,
)
from iddx_core.results import ResultsReader, find_results, build_label_map
from iddx_core.utils import new_guid

from hec22_calculator import (
    size_inlet_from_iddx, Hec22Result, GRATE_TYPE_NAMES,
)

SQ_MI_TO_M2 = 2_589_988.0
HEC22_TYPE_NAMES = {0: "Grate", 1: "Curb", 2: "Combo", 3: "Slotted"}
ICAP_NAMES = {0: "None", 1: "Low/High", 2: "Rated", 3: "HEC-22"}


# ── Approach flow helpers ────────────────────────────────────────────────

def _catchments_to_node(phase: Phase) -> dict[str, list]:
    """Map node GUID -> list of catchments that drain to it."""
    mapping: dict[str, list] = {}
    for c in phase.catchments:
        if c.to_dest_guid:
            mapping.setdefault(c.to_dest_guid, []).append(c)
    return mapping


def _rational_flow(catchments, intensity_mm_hr: float) -> float:
    """Rational method: Q = C*i*A (metric)."""
    total = 0.0
    for c in catchments:
        A_m2 = c.area * SQ_MI_TO_M2
        Q = c.cv * (intensity_mm_hr / 3_600_000.0) * A_m2
        total += Q
    return total


def _get_swmm_inflows(model: IddxModel, phase: Phase,
                      return_period: float) -> dict[str, float]:
    """Get peak lateral inflow per node from SWMM results."""
    result_files = find_results(model._filepath)
    label_map = build_label_map(model)

    phase_files = result_files.get(phase.label, [])
    rp_str = f"_{return_period:.3f}_"

    target_file = None
    for f in phase_files:
        if rp_str in f.name:
            target_file = f
            break
    if not phase_files:
        return {}
    if target_file is None:
        target_file = phase_files[0]

    reader = ResultsReader(str(target_file))
    inflows: dict[str, float] = {}
    for ns in reader.all_node_summaries(label_map):
        inflows[ns.guid] = ns.peak_lateral_inflow
    return inflows


# ── GUI Application ──────────────────────────────────────────────────────

class InletBypassApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("InfoDrainage Inlet & Bypass Tool")
        self.root.geometry("1100x780")
        self.root.minsize(900, 600)

        self.model: Optional[IddxModel] = None
        self.phase: Optional[Phase] = None
        self.sizing_results: list[dict] = []

        self._build_ui()

    def _build_ui(self):
        # Top frame: file + phase
        top = ttk.LabelFrame(self.root, text="Model", padding=8)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(top, text="File:").grid(row=0, column=0, sticky=tk.W)
        self.file_var = tk.StringVar()
        file_entry = ttk.Entry(top, textvariable=self.file_var, width=70)
        file_entry.grid(row=0, column=1, padx=4, sticky=tk.EW)
        ttk.Button(top, text="Browse...", command=self._browse_file).grid(
            row=0, column=2, padx=4)
        ttk.Button(top, text="Load", command=self._load_model).grid(
            row=0, column=3, padx=4)

        ttk.Label(top, text="Phase:").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        self.phase_var = tk.StringVar()
        self.phase_combo = ttk.Combobox(top, textvariable=self.phase_var,
                                        state="readonly", width=40)
        self.phase_combo.grid(row=1, column=1, padx=4, sticky=tk.W, pady=(4, 0))
        self.phase_combo.bind("<<ComboboxSelected>>", self._on_phase_changed)
        top.columnconfigure(1, weight=1)

        # Action selector
        action_frame = ttk.LabelFrame(self.root, text="Action", padding=8)
        action_frame.pack(fill=tk.X, padx=8, pady=4)

        self.action_var = tk.StringVar(value="size")
        actions = [
            ("HEC-22 Sizing", "size"),
            ("Report", "report"),
            ("Audit", "audit"),
            ("Export CSV", "export"),
        ]
        for i, (label, val) in enumerate(actions):
            ttk.Radiobutton(action_frame, text=label, variable=self.action_var,
                            value=val, command=self._on_action_changed).grid(
                row=0, column=i, padx=12)

        # Options frame (shown/hidden based on action)
        self.options_frame = ttk.LabelFrame(self.root, text="HEC-22 Sizing Options",
                                            padding=8)
        self.options_frame.pack(fill=tk.X, padx=8, pady=4)

        # Flow source
        ttk.Label(self.options_frame, text="Flow Source:").grid(
            row=0, column=0, sticky=tk.W)
        self.flow_source_var = tk.StringVar(value="rational")
        ttk.Radiobutton(self.options_frame, text="Rational Method",
                        variable=self.flow_source_var, value="rational",
                        command=self._on_flow_source_changed).grid(
            row=0, column=1, padx=4)
        ttk.Radiobutton(self.options_frame, text="SWMM Results",
                        variable=self.flow_source_var, value="swmm",
                        command=self._on_flow_source_changed).grid(
            row=0, column=2, padx=4)

        # Rational method options
        self.rational_frame = ttk.Frame(self.options_frame)
        self.rational_frame.grid(row=1, column=0, columnspan=4, sticky=tk.W,
                                 pady=(4, 0))
        ttk.Label(self.rational_frame, text="Rainfall Intensity:").pack(
            side=tk.LEFT)
        self.intensity_var = tk.StringVar(value="50.0")
        ttk.Entry(self.rational_frame, textvariable=self.intensity_var,
                  width=10).pack(side=tk.LEFT, padx=4)
        ttk.Label(self.rational_frame, text="mm/hr").pack(side=tk.LEFT)

        # SWMM results options
        self.swmm_frame = ttk.Frame(self.options_frame)
        self.swmm_frame.grid(row=2, column=0, columnspan=4, sticky=tk.W,
                             pady=(4, 0))
        ttk.Label(self.swmm_frame, text="Return Period:").pack(side=tk.LEFT)
        self.rp_var = tk.StringVar(value="100")
        self.rp_combo = ttk.Combobox(self.swmm_frame, textvariable=self.rp_var,
                                     width=10, values=["2", "10", "25", "50", "100"])
        self.rp_combo.pack(side=tk.LEFT, padx=4)
        ttk.Label(self.swmm_frame, text="year").pack(side=tk.LEFT)
        self.swmm_frame.grid_remove()

        # Edit options row
        edit_frame = ttk.Frame(self.options_frame)
        edit_frame.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))

        ttk.Label(edit_frame, text="Override Clogging (%):").pack(side=tk.LEFT)
        self.clog_override_var = tk.StringVar(value="")
        ttk.Entry(edit_frame, textvariable=self.clog_override_var, width=6).pack(
            side=tk.LEFT, padx=(4, 16))

        ttk.Label(edit_frame, text="Max Spread (m):").pack(side=tk.LEFT)
        self.max_spread_var = tk.StringVar(value="3.0")
        ttk.Entry(edit_frame, textvariable=self.max_spread_var, width=6).pack(
            side=tk.LEFT, padx=4)

        # Run + Save buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(btn_frame, text="Run", command=self._run_action,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Export Results to CSV...",
                   command=self._export_csv).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Save Model As...",
                   command=self._save_model).pack(side=tk.LEFT, padx=4)

        self.status_var = tk.StringVar(value="Ready - select an .iddx file to begin")
        ttk.Label(btn_frame, textvariable=self.status_var,
                  foreground="gray").pack(side=tk.RIGHT, padx=4)

        # Results area with notebook for table + text views
        results_nb = ttk.Notebook(self.root)
        results_nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        # Table view
        table_frame = ttk.Frame(results_nb)
        results_nb.add(table_frame, text="Results Table")

        self.tree = ttk.Treeview(table_frame, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        # Text view
        text_frame = ttk.Frame(results_nb)
        results_nb.add(text_frame, text="Text Output")
        self.text_output = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD,
                                                      font=("Consolas", 9))
        self.text_output.pack(fill=tk.BOTH, expand=True)

    # ── File / Phase ─────────────────────────────────────────────────────

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select InfoDrainage Model",
            filetypes=[("InfoDrainage files", "*.iddx"), ("All files", "*.*")],
        )
        if path:
            self.file_var.set(path)
            self._load_model()

    def _load_model(self):
        path = self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Error", "Please select a valid .iddx file.")
            return

        try:
            self.model = IddxModel.open(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load model:\n{e}")
            return

        phases = [p.label for p in self.model.phases.values()]
        self.phase_combo["values"] = phases
        if phases:
            self.phase_combo.current(0)
            self._on_phase_changed()

        n_phases = len(phases)
        self.status_var.set(f"Loaded: {os.path.basename(path)} ({n_phases} phases)")

    def _on_phase_changed(self, event=None):
        if not self.model:
            return
        label = self.phase_var.get()
        for p in self.model.phases.values():
            if p.label == label:
                self.phase = p
                break

    # ── Action switching ─────────────────────────────────────────────────

    def _on_action_changed(self):
        action = self.action_var.get()
        if action == "size":
            self.options_frame.pack(fill=tk.X, padx=8, pady=4,
                                    before=self.root.winfo_children()[3])
        else:
            self.options_frame.pack_forget()

    def _on_flow_source_changed(self):
        if self.flow_source_var.get() == "rational":
            self.rational_frame.grid()
            self.swmm_frame.grid_remove()
        else:
            self.rational_frame.grid_remove()
            self.swmm_frame.grid()

    # ── Run actions ──────────────────────────────────────────────────────

    def _run_action(self):
        if not self.model or not self.phase:
            messagebox.showwarning("Warning", "Load a model and select a phase first.")
            return

        action = self.action_var.get()
        try:
            if action == "size":
                self._run_sizing()
            elif action == "report":
                self._run_report()
            elif action == "audit":
                self._run_audit()
            elif action == "export":
                self._run_export()
        except Exception as e:
            messagebox.showerror("Error", f"Action failed:\n{e}")
            import traceback
            traceback.print_exc()

    def _run_sizing(self):
        phase = self.phase
        cat_map = _catchments_to_node(phase)

        # Resolve approach flows
        flows: dict[str, float] = {}
        if self.flow_source_var.get() == "rational":
            try:
                intensity = float(self.intensity_var.get())
            except ValueError:
                messagebox.showerror("Error", "Invalid rainfall intensity.")
                return
            for node_guid, cats in cat_map.items():
                flows[node_guid] = _rational_flow(cats, intensity)
        else:
            try:
                rp = float(self.rp_var.get())
            except ValueError:
                messagebox.showerror("Error", "Invalid return period.")
                return
            flows = _get_swmm_inflows(self.model, phase, rp)
            if not flows:
                messagebox.showwarning("Warning",
                    "No SWMM results found. Falling back to rational method.")
                self.flow_source_var.set("rational")
                return

        clog_override = None
        clog_str = self.clog_override_var.get().strip()
        if clog_str:
            try:
                clog_override = float(clog_str)
            except ValueError:
                pass

        try:
            max_spread = float(self.max_spread_var.get())
        except ValueError:
            max_spread = 3.0

        # Run sizing
        results = []
        for jn in phase.junctions:
            for inlet in jn.inlets:
                if inlet.hec22_config is None:
                    continue
                Q = flows.get(jn.guid, 0.0)
                # Also add flow from bypass connections arriving at this node
                for conn in phase.connections:
                    if conn.is_bypass and conn.to_junction_guid == jn.guid:
                        src_guid = conn.from_junction_guid
                        if src_guid in flows:
                            pass  # upstream bypass flow handled by chain

                if clog_override is not None and inlet.hec22_config.inlet_params:
                    p = inlet.hec22_config.inlet_params
                    if hasattr(p, "clogging"):
                        p.clogging = clog_override

                result = size_inlet_from_iddx(inlet, Q)
                itype = HEC22_TYPE_NAMES.get(
                    inlet.hec22_config.hec22_inlet_type, "?")

                spread_flag = ""
                if result.spread > max_spread and max_spread > 0:
                    spread_flag = "EXCEEDS"

                src_labels = ", ".join(s.label for s in inlet.sources)

                results.append({
                    "Node": jn.label,
                    "Inlet": inlet.label,
                    "Type": itype,
                    "Q Approach (m3/s)": f"{result.approach_flow:.6f}",
                    "Q Captured (m3/s)": f"{result.captured_flow:.6f}",
                    "Q Bypass (m3/s)": f"{result.bypass_flow:.6f}",
                    "Efficiency (%)": f"{result.efficiency * 100:.1f}",
                    "Spread (m)": f"{result.spread:.3f}",
                    "Spread Flag": spread_flag,
                    "Depth (m)": f"{result.gutter_depth:.4f}",
                    "Velocity (m/s)": f"{result.velocity:.3f}",
                    "Bypass To": inlet.bypass_dest_label,
                    "Sources": src_labels,
                    "_result": result,
                })

        self.sizing_results = results
        self._show_table(results, exclude_cols=["_result"])
        self._show_text_sizing(results)
        self.status_var.set(f"Sized {len(results)} HEC-22 inlets")

    def _run_report(self):
        phase = self.phase
        lines = []
        lines.append(f"Phase: {phase.label}")
        lines.append(f"Junctions: {len(phase.junctions)}")
        lines.append(f"Connections: {len(phase.connections)}")

        bypass = [c for c in phase.connections if c.is_bypass]
        lines.append(f"Bypass connections: {len(bypass)}")

        hec22_count = 0
        total_inlets = 0
        for jn in phase.junctions:
            for inlet in jn.inlets:
                total_inlets += 1
                if inlet.hec22_config:
                    hec22_count += 1
        for ds in phase.drainage_systems:
            for inlet in ds.inlets:
                total_inlets += 1
                if inlet.hec22_config:
                    hec22_count += 1

        lines.append(f"Total inlets: {total_inlets}")
        lines.append(f"HEC-22 configured: {hec22_count}")
        lines.append(f"Non-HEC-22: {total_inlets - hec22_count}")
        lines.append("")

        # Inlet details
        for jn in sorted(phase.junctions, key=lambda j: j.label):
            for inlet in jn.inlets:
                if not inlet.hec22_config:
                    continue
                cfg = inlet.hec22_config
                itype = HEC22_TYPE_NAMES.get(cfg.hec22_inlet_type, "?")
                gutter = ""
                if cfg.gutter:
                    gutter = (f"Slope=1:{cfg.gutter.slope:.1f} "
                              f"W={cfg.gutter.width:.4f}m "
                              f"n={cfg.gutter.mannings_n}")
                bypass_label = inlet.bypass_dest_label or "(none)"
                lines.append(f"{jn.label} [{inlet.label}]")
                lines.append(f"  Type: {itype}  |  {gutter}")
                lines.append(f"  Bypass to: {bypass_label}")
                src = ", ".join(s.label for s in inlet.sources)
                lines.append(f"  Sources: {src}")
                lines.append("")

        if bypass:
            lines.append("BYPASS CONNECTIONS:")
            for bc in sorted(bypass, key=lambda c: c.label):
                lines.append(f"  {bc.label}: {bc.from_junction_label} -> "
                             f"{bc.to_junction_label}  L={bc.length:.1f}m")

        self._show_text("\n".join(lines))
        self.status_var.set("Report generated")

    def _run_audit(self):
        phase = self.phase
        lines = []
        errors = 0
        warnings = 0
        conn_guids = {c.guid for c in phase.connections}

        for jn in phase.junctions:
            for inlet in jn.inlets:
                if inlet.capacity_type == 3 and not inlet.hec22_config:
                    lines.append(f"ERROR: {jn.label} [{inlet.label}] - "
                                 f"ICapType=HEC-22 but no config")
                    errors += 1
                if inlet.bypass_dest_guid and inlet.bypass_dest_guid not in conn_guids:
                    lines.append(f"ERROR: {jn.label} [{inlet.label}] - "
                                 f"bypass GUID not found in connections")
                    errors += 1
                if inlet.hec22_config and inlet.hec22_config.inlet_params:
                    p = inlet.hec22_config.inlet_params
                    if hasattr(p, "clogging") and p.clogging >= 100:
                        lines.append(f"ERROR: {jn.label} [{inlet.label}] - "
                                     f"100% clogging")
                        errors += 1
                    elif hasattr(p, "clogging") and p.clogging > 50:
                        lines.append(f"WARNING: {jn.label} [{inlet.label}] - "
                                     f"clogging {p.clogging}%")
                        warnings += 1

        lines.insert(0, f"Audit: {errors} errors, {warnings} warnings\n")
        if not errors and not warnings:
            lines.append("All checks passed.")

        self._show_text("\n".join(lines))
        self.status_var.set(f"Audit: {errors} errors, {warnings} warnings")

    def _run_export(self):
        path = filedialog.asksaveasfilename(
            title="Export Inlet Schedule",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return

        phase = self.phase
        rows = []
        for jn in sorted(phase.junctions, key=lambda j: j.label):
            for inlet in jn.inlets:
                cfg = inlet.hec22_config
                row = {
                    "Node": jn.label,
                    "Inlet": inlet.label,
                    "Capacity Type": ICAP_NAMES.get(inlet.capacity_type, "?"),
                    "HEC-22 Type": HEC22_TYPE_NAMES.get(
                        cfg.hec22_inlet_type, "") if cfg else "",
                }
                if cfg and cfg.gutter:
                    g = cfg.gutter
                    row["Gutter Slope (1:X)"] = f"{g.slope:.2f}"
                    row["Gutter Width (m)"] = f"{g.width:.4f}"
                    row["Manning n"] = f"{g.mannings_n}"
                p = cfg.inlet_params if cfg else None
                if p:
                    if hasattr(p, "grate_length"):
                        row["Grate Length (m)"] = f"{p.grate_length:.6f}"
                    if hasattr(p, "width"):
                        row["Grate Width (m)"] = f"{p.width:.6f}"
                    if hasattr(p, "depression"):
                        row["Depression (mm)"] = f"{p.depression:.1f}"
                    if hasattr(p, "clogging"):
                        row["Clogging (%)"] = f"{p.clogging:.1f}"
                row["Bypass To"] = inlet.bypass_dest_label
                row["Sources"] = ", ".join(s.label for s in inlet.sources)
                rows.append(row)

        if rows:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            self.status_var.set(f"Exported {len(rows)} inlets to {os.path.basename(path)}")
            messagebox.showinfo("Export", f"Saved {len(rows)} inlets to:\n{path}")
        else:
            messagebox.showinfo("Export", "No inlet data to export.")

    # ── Display helpers ──────────────────────────────────────────────────

    def _show_table(self, rows: list[dict], exclude_cols: Optional[list] = None):
        self.tree.delete(*self.tree.get_children())
        if not rows:
            return

        exclude = set(exclude_cols or [])
        cols = [k for k in rows[0].keys() if k not in exclude]
        self.tree["columns"] = cols
        for col in cols:
            width = max(80, min(len(col) * 9, 200))
            self.tree.heading(col, text=col,
                              command=lambda c=col: self._sort_tree(c))
            self.tree.column(col, width=width, minwidth=60)

        for row in rows:
            vals = [row.get(c, "") for c in cols]
            tag = ""
            if row.get("Spread Flag") == "EXCEEDS":
                tag = "warn"
            self.tree.insert("", tk.END, values=vals, tags=(tag,))

        self.tree.tag_configure("warn", background="#FFE0E0")

    def _sort_tree(self, col):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        try:
            items.sort(key=lambda t: float(t[0]))
        except ValueError:
            items.sort(key=lambda t: t[0])
        for idx, (_, k) in enumerate(items):
            self.tree.move(k, "", idx)

    def _show_text(self, text: str):
        self.text_output.delete("1.0", tk.END)
        self.text_output.insert(tk.END, text)

    def _show_text_sizing(self, results: list[dict]):
        lines = [f"HEC-22 Sizing Results ({len(results)} inlets)\n"]
        lines.append(f"{'Node':<15} {'Type':<8} {'Q_in':>10} {'Q_cap':>10} "
                     f"{'Q_byp':>10} {'Eff%':>6} {'Spread':>8} {'Flag':<8}")
        lines.append("-" * 85)
        for r in results:
            lines.append(
                f"{r['Node']:<15} {r['Type']:<8} {r['Q Approach (m3/s)']:>10} "
                f"{r['Q Captured (m3/s)']:>10} {r['Q Bypass (m3/s)']:>10} "
                f"{r['Efficiency (%)']:>6} {r['Spread (m)']:>8} "
                f"{r['Spread Flag']:<8}"
            )

        exceeds = sum(1 for r in results if r.get("Spread Flag") == "EXCEEDS")
        if exceeds:
            lines.append(f"\n{exceeds} inlets EXCEED max spread limit.")

        self._show_text("\n".join(lines))

    # ── Save / Export ────────────────────────────────────────────────────

    def _export_csv(self):
        if not self.sizing_results:
            messagebox.showinfo("Export", "Run sizing first to generate results.")
            return

        path = filedialog.asksaveasfilename(
            title="Export Sizing Results",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return

        rows = self.sizing_results
        exclude = {"_result"}
        cols = [k for k in rows[0].keys() if k not in exclude]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        self.status_var.set(f"Exported {len(rows)} results to {os.path.basename(path)}")
        messagebox.showinfo("Export", f"Saved {len(rows)} results to:\n{path}")

    def _save_model(self):
        if not self.model:
            messagebox.showwarning("Warning", "No model loaded.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Model As",
            defaultextension=".iddx",
            filetypes=[("InfoDrainage files", "*.iddx")],
        )
        if not path:
            return

        try:
            self.model.save(path)
            self.status_var.set(f"Saved to {os.path.basename(path)}")
            messagebox.showinfo("Save", f"Model saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")


def main():
    root = tk.Tk()
    try:
        root.tk.call("source", os.path.join(
            os.path.dirname(__file__), "..", "azure.tcl"))
        root.tk.call("set_theme", "light")
    except tk.TclError:
        pass

    style = ttk.Style()
    try:
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
    except tk.TclError:
        pass

    InletBypassApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
