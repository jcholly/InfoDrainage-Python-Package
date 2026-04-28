"""Read InfoDrainage simulation results from SWMM-format .out binary files."""

from __future__ import annotations

import datetime
import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .exceptions import ResultsError, ElementNotFoundError

logger = logging.getLogger("iddx_core.results")

SWMM_MAGIC = 516114522

# Hostile-file caps. SWMM element IDs are documented as ≤21 chars; 256 is a generous bound.
_MAX_STRING_LEN = 256
_MAX_RESULTS_BYTES = 4 * 1024 * 1024 * 1024  # 4 GB ceiling on .out file size

# CSV cells beginning with these chars execute as formulas in Excel/LibreOffice.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Escape a value to prevent CSV formula injection in spreadsheet apps."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _CSV_FORMULA_PREFIXES:
        return "'" + s
    return s


FLOW_UNIT_LABELS = {0: "CFS", 1: "GPM", 2: "MGD", 3: "CMS", 4: "LPS", 5: "LPD"}

NODE_VARIABLES = {
    0: "depth_above_invert",
    1: "hydraulic_head",
    2: "volume_stored",
    3: "lateral_inflow",
    4: "total_inflow",
    5: "flooding",
}

LINK_VARIABLES = {
    0: "flow_rate",
    1: "flow_depth",
    2: "flow_velocity",
    3: "froude_number",
    4: "capacity",
}

SYSTEM_VARIABLES = {
    0: "air_temperature",
    1: "rainfall",
    2: "snow_depth",
    3: "evap_infil_loss",
    4: "runoff",
    5: "dry_weather_inflow",
    6: "groundwater_inflow",
    7: "rdii_inflow",
    8: "direct_inflow",
    9: "total_lateral_inflow",
    10: "flood_losses",
    11: "outfall_flow",
    12: "stored_volume",
    13: "evaporation_rate",
    14: "potential_pet",
}


@dataclass
class TimeSeries:
    """A time series of simulation results for a single variable."""

    element_id: str
    element_label: str
    variable: str
    times: list[datetime.datetime]
    values: list[float]

    @property
    def peak(self) -> float:
        return max(self.values) if self.values else 0.0

    @property
    def peak_time(self) -> Optional[datetime.datetime]:
        if not self.values:
            return None
        idx = self.values.index(max(self.values))
        return self.times[idx]

    @property
    def min(self) -> float:
        return min(self.values) if self.values else 0.0

    @property
    def mean(self) -> float:
        return sum(self.values) / len(self.values) if self.values else 0.0

    @property
    def total(self) -> float:
        return sum(self.values)

    def to_csv_rows(self) -> list[list]:
        rows = [["Time", _csv_safe(self.variable)]]
        for t, v in zip(self.times, self.values):
            rows.append([t.isoformat(), f"{v:.6f}"])
        return rows

    def to_csv(self, filepath: str | Path) -> None:
        """Write time series to a CSV file."""
        import csv

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(self.to_csv_rows())

    def to_dict(self) -> dict:
        """Convert to a dict suitable for DataFrame construction."""
        return {
            "time": list(self.times),
            self.variable: list(self.values),
        }


@dataclass
class NodeSummary:
    """Peak results for a single node."""

    guid: str
    label: str
    node_type: int
    invert_elevation: float
    max_depth: float
    peak_depth: float = 0.0
    peak_head: float = 0.0
    peak_lateral_inflow: float = 0.0
    peak_total_inflow: float = 0.0
    peak_flooding: float = 0.0
    time_of_peak_flooding: Optional[datetime.datetime] = None


@dataclass
class LinkSummary:
    """Peak results for a single link."""

    guid: str
    label: str
    link_type: int
    peak_flow: float = 0.0
    peak_depth: float = 0.0
    peak_velocity: float = 0.0
    max_capacity: float = 0.0
    time_of_peak_flow: Optional[datetime.datetime] = None


class ResultsReader:
    """Read simulation results from an InfoDrainage .out file (SWMM binary format).

    Results files are located in a subfolder next to the .iddx file, named
    ``{Phase}_{ReturnPeriod}_{Duration}.out``.
    """

    def __init__(self, filepath: str | Path):
        self._path = Path(filepath)
        if not self._path.exists():
            raise ResultsError("Results file not found", filepath=str(self._path))

        size = self._path.stat().st_size
        if size > _MAX_RESULTS_BYTES:
            raise ResultsError(
                f"Results file too large ({size} bytes > {_MAX_RESULTS_BYTES})",
                filepath=str(self._path),
            )
        if size < 28:
            raise ResultsError(
                "Results file too small to be valid SWMM output",
                filepath=str(self._path),
            )

        with open(self._path, "rb") as f:
            self._data = f.read()

        self._parse_header()
        self._parse_trailer()
        self._sanity_check_counts()
        self._parse_names()
        self._parse_properties()
        self._parse_variables()
        self._parse_timing()
        self._validate()

        self._node_id_to_idx: dict[str, int] = {
            nid: i for i, nid in enumerate(self._node_ids)
        }
        self._link_id_to_idx: dict[str, int] = {
            lid: i for i, lid in enumerate(self._link_ids)
        }
        self._node_var_idx: dict[str, int] = {
            NODE_VARIABLES.get(c, f"var_{c}"): i
            for i, c in enumerate(self._node_var_codes)
        }
        self._link_var_idx: dict[str, int] = {
            LINK_VARIABLES.get(c, f"var_{c}"): i
            for i, c in enumerate(self._link_var_codes)
        }

    def _sanity_check_counts(self):
        """Reject hostile counts/offsets before any allocation-driving parsing.

        A malicious .out header can declare counts like 0x7FFFFFFF that would
        cause unbounded allocation or seek into attacker-chosen offsets via
        Python's negative-index-from-end semantics in struct.unpack_from.
        """
        size = len(self._data)
        for name, val in (
            ("n_subcatch", self._n_subcatch),
            ("n_nodes", self._n_nodes),
            ("n_links", self._n_links),
            ("n_pollutants", self._n_pollutants),
            ("n_periods", self._n_periods),
        ):
            if val < 0 or val * 4 > size:
                raise ResultsError(
                    f"Implausible {name}={val} for file size {size}",
                    filepath=str(self._path),
                )
        for name, off in (
            ("names_start", self._names_start),
            ("props_start", self._props_start),
            ("results_start", self._results_start),
        ):
            if not (0 <= off < size):
                raise ResultsError(
                    f"Section offset {name}={off} out of range [0, {size})",
                    filepath=str(self._path),
                )

    def _parse_header(self):
        magic = struct.unpack_from("<i", self._data, 0)[0]
        if magic != SWMM_MAGIC:
            raise ResultsError(
                f"Not a SWMM output file (magic={magic})", filepath=str(self._path)
            )

        (
            self._version,
            flow_code,
            self._n_subcatch,
            self._n_nodes,
            self._n_links,
            self._n_pollutants,
        ) = struct.unpack_from("<6i", self._data, 4)

        self.flow_units = FLOW_UNIT_LABELS.get(flow_code, f"unknown({flow_code})")

    def _parse_trailer(self):
        (
            self._names_start,
            self._props_start,
            self._results_start,
            self._n_periods,
            self._error_code,
            magic2,
        ) = struct.unpack_from("<6i", self._data, len(self._data) - 24)

        if magic2 != SWMM_MAGIC:
            raise ResultsError(
                "Corrupted results file (bad trailing magic)", filepath=str(self._path)
            )
        if self._error_code != 0:
            raise ResultsError(
                f"Simulation error code: {self._error_code}", filepath=str(self._path)
            )
        if self._n_periods == 0:
            raise ResultsError(
                "No reporting periods in results file", filepath=str(self._path)
            )

    def _read_string(self, offset: int) -> tuple[str, int]:
        if offset < 0 or offset + 4 > len(self._data):
            raise ResultsError(
                f"String offset {offset} out of range", filepath=str(self._path)
            )
        slen = struct.unpack_from("<i", self._data, offset)[0]
        if slen < 0 or slen > _MAX_STRING_LEN:
            raise ResultsError(
                f"Implausible string length {slen} (max {_MAX_STRING_LEN})",
                filepath=str(self._path),
            )
        end = offset + 4 + slen
        if end > len(self._data):
            raise ResultsError(
                f"String at offset {offset} extends past end of file",
                filepath=str(self._path),
            )
        s = self._data[offset + 4 : end].decode("ascii", errors="replace")
        return s, end

    def _parse_names(self):
        off = self._names_start

        self._subcatch_ids: list[str] = []
        for _ in range(self._n_subcatch):
            name, off = self._read_string(off)
            self._subcatch_ids.append(name)

        self._node_ids: list[str] = []
        for _ in range(self._n_nodes):
            name, off = self._read_string(off)
            self._node_ids.append(name)

        self._link_ids: list[str] = []
        for _ in range(self._n_links):
            name, off = self._read_string(off)
            self._link_ids.append(name)

    def _parse_properties(self):
        off = self._props_start

        # Subcatchment properties
        n_subcatch_props = struct.unpack_from("<i", self._data, off)[0]
        off += 4
        if n_subcatch_props > 0:
            off += n_subcatch_props * 4
            off += self._n_subcatch * n_subcatch_props * 4

        # Node properties
        n_node_props = struct.unpack_from("<i", self._data, off)[0]
        off += 4
        self._node_prop_codes = struct.unpack_from(f"<{n_node_props}i", self._data, off)
        off += n_node_props * 4

        self._node_props: list[tuple[float, ...]] = []
        for _ in range(self._n_nodes):
            props = struct.unpack_from(f"<{n_node_props}f", self._data, off)
            off += n_node_props * 4
            self._node_props.append(props)

        # Link properties
        n_link_props = struct.unpack_from("<i", self._data, off)[0]
        off += 4
        self._link_prop_codes = struct.unpack_from(f"<{n_link_props}i", self._data, off)
        off += n_link_props * 4

        self._link_props: list[tuple[float, ...]] = []
        for _ in range(self._n_links):
            props = struct.unpack_from(f"<{n_link_props}f", self._data, off)
            off += n_link_props * 4
            self._link_props.append(props)

        self._props_end = off

    def _parse_variables(self):
        off = self._props_end

        self._n_subcatch_vars = struct.unpack_from("<i", self._data, off)[0]
        off += 4
        if self._n_subcatch_vars:
            off += self._n_subcatch_vars * 4

        self._n_node_vars = struct.unpack_from("<i", self._data, off)[0]
        off += 4
        self._node_var_codes = struct.unpack_from(
            f"<{self._n_node_vars}i", self._data, off
        )
        off += self._n_node_vars * 4

        self._n_link_vars = struct.unpack_from("<i", self._data, off)[0]
        off += 4
        self._link_var_codes = struct.unpack_from(
            f"<{self._n_link_vars}i", self._data, off
        )
        off += self._n_link_vars * 4

        self._n_sys_vars = struct.unpack_from("<i", self._data, off)[0]
        off += 4
        if self._n_sys_vars:
            off += self._n_sys_vars * 4

        self._vars_end = off

    def _parse_timing(self):
        off = self._vars_end

        raw_date = struct.unpack_from("<d", self._data, off)[0]
        off += 8
        days = int(raw_date)
        seconds = int((raw_date - days) * 86400)
        self._start_date = datetime.datetime(1899, 12, 30) + datetime.timedelta(
            days=days, seconds=seconds
        )

        self._report_interval = struct.unpack_from("<i", self._data, off)[0]
        off += 4

        self._bytes_per_period = 4 * (
            2
            + self._n_subcatch * self._n_subcatch_vars
            + self._n_nodes * self._n_node_vars
            + self._n_links * self._n_link_vars
            + self._n_sys_vars
        )

    def _validate(self):
        expected_size = (
            self._results_start + self._n_periods * self._bytes_per_period + 24
        )
        if expected_size != len(self._data):
            raise ResultsError(
                f"File size mismatch: expected {expected_size}, got {len(self._data)}",
                filepath=str(self._path),
            )

    def _period_time(self, period: int) -> datetime.datetime:
        poff = self._results_start + period * self._bytes_per_period
        raw = struct.unpack_from("<d", self._data, poff)[0]
        days = int(raw)
        seconds = int((raw - days) * 86400)
        return datetime.datetime(1899, 12, 30) + datetime.timedelta(
            days=days, seconds=seconds
        )

    def _node_result(self, node_idx: int, var_idx: int, period: int) -> float:
        offset = (
            self._results_start
            + period * self._bytes_per_period
            + 8
            + (node_idx * self._n_node_vars + var_idx) * 4
        )
        return struct.unpack_from("<f", self._data, offset)[0]

    def _link_result(self, link_idx: int, var_idx: int, period: int) -> float:
        offset = (
            self._results_start
            + period * self._bytes_per_period
            + 8
            + self._n_nodes * self._n_node_vars * 4
            + (link_idx * self._n_link_vars + var_idx) * 4
        )
        return struct.unpack_from("<f", self._data, offset)[0]

    def _system_result(self, var_idx: int, period: int) -> float:
        offset = (
            self._results_start
            + period * self._bytes_per_period
            + 8
            + self._n_nodes * self._n_node_vars * 4
            + self._n_links * self._n_link_vars * 4
            + var_idx * 4
        )
        return struct.unpack_from("<f", self._data, offset)[0]

    # ---- Public properties ----

    @property
    def num_periods(self) -> int:
        return self._n_periods

    @property
    def report_interval_seconds(self) -> int:
        return self._report_interval

    @property
    def start_time(self) -> datetime.datetime:
        return self._start_date

    @property
    def end_time(self) -> datetime.datetime:
        return self._start_date + datetime.timedelta(
            seconds=self._report_interval * (self._n_periods - 1)
        )

    @property
    def node_ids(self) -> list[str]:
        return list(self._node_ids)

    @property
    def link_ids(self) -> list[str]:
        return list(self._link_ids)

    @property
    def node_variables(self) -> list[str]:
        return [NODE_VARIABLES.get(c, f"var_{c}") for c in self._node_var_codes]

    @property
    def link_variables(self) -> list[str]:
        return [LINK_VARIABLES.get(c, f"var_{c}") for c in self._link_var_codes]

    @property
    def system_variables(self) -> list[str]:
        return [
            SYSTEM_VARIABLES.get(i, f"sys_var_{i}") for i in range(self._n_sys_vars)
        ]

    # ---- Time series extraction ----

    def system_time_series(self, variable: str = "rainfall") -> TimeSeries:
        """Get a system-level time series (rainfall, runoff, flooding, etc.)."""
        var_names = self.system_variables
        if variable not in var_names:
            raise KeyError(f"Variable '{variable}' not available. Options: {var_names}")
        var_idx = var_names.index(variable)

        times = []
        values = []
        for p in range(self._n_periods):
            times.append(self._period_time(p))
            values.append(self._system_result(var_idx, p))

        return TimeSeries(
            element_id="system",
            element_label="System",
            variable=variable,
            times=times,
            values=values,
        )

    def node_time_series(
        self, node_id: str, variable: str = "total_inflow", label: str = ""
    ) -> TimeSeries:
        """Get a time series for a node variable.

        Args:
            node_id: GUID of the node (from the .iddx model).
            variable: One of the node_variables names.
            label: Human-readable label (optional).
        """
        node_idx = self._node_id_to_idx.get(node_id)
        if node_idx is None:
            raise ElementNotFoundError("Node", node_id)

        var_idx = self._node_var_idx.get(variable)
        if var_idx is None:
            raise KeyError(
                f"Variable '{variable}' not available. Options: {list(self._node_var_idx)}"
            )

        times = []
        values = []
        for p in range(self._n_periods):
            times.append(self._period_time(p))
            values.append(self._node_result(node_idx, var_idx, p))

        return TimeSeries(
            element_id=node_id,
            element_label=label or node_id,
            variable=variable,
            times=times,
            values=values,
        )

    def link_time_series(
        self, link_id: str, variable: str = "flow_rate", label: str = ""
    ) -> TimeSeries:
        """Get a time series for a link variable.

        Args:
            link_id: GUID of the link (from the .iddx model).
            variable: One of the link_variables names.
            label: Human-readable label (optional).
        """
        link_idx = self._link_id_to_idx.get(link_id)
        if link_idx is None:
            raise ElementNotFoundError("Link", link_id)

        var_idx = self._link_var_idx.get(variable)
        if var_idx is None:
            raise KeyError(
                f"Variable '{variable}' not available. Options: {list(self._link_var_idx)}"
            )

        times = []
        values = []
        for p in range(self._n_periods):
            times.append(self._period_time(p))
            values.append(self._link_result(link_idx, var_idx, p))

        return TimeSeries(
            element_id=link_id,
            element_label=label or link_id,
            variable=variable,
            times=times,
            values=values,
        )

    # ---- Summaries ----

    def node_summary(self, node_id: str, label: str = "") -> NodeSummary:
        """Get peak results summary for a node."""
        idx = self._node_id_to_idx.get(node_id)
        if idx is None:
            raise ElementNotFoundError("Node", node_id)

        prop_codes = self._node_prop_codes
        props = self._node_props[idx]
        node_type = int(props[list(prop_codes).index(0)]) if 0 in prop_codes else 0
        inv_elev = props[list(prop_codes).index(2)] if 2 in prop_codes else 0.0
        max_depth = props[list(prop_codes).index(3)] if 3 in prop_codes else 0.0

        depth_idx = self._node_var_idx.get("depth_above_invert")
        head_idx = self._node_var_idx.get("hydraulic_head")
        lateral_idx = self._node_var_idx.get("lateral_inflow")
        total_idx = self._node_var_idx.get("total_inflow")
        flood_idx = self._node_var_idx.get("flooding")

        summary = NodeSummary(
            guid=node_id,
            label=label or node_id,
            node_type=node_type,
            invert_elevation=inv_elev,
            max_depth=max_depth,
        )

        for p in range(self._n_periods):
            if depth_idx is not None:
                v = self._node_result(idx, depth_idx, p)
                if v > summary.peak_depth:
                    summary.peak_depth = v

            if head_idx is not None:
                v = self._node_result(idx, head_idx, p)
                if v > summary.peak_head:
                    summary.peak_head = v

            if lateral_idx is not None:
                v = self._node_result(idx, lateral_idx, p)
                if v > summary.peak_lateral_inflow:
                    summary.peak_lateral_inflow = v

            if total_idx is not None:
                v = self._node_result(idx, total_idx, p)
                if v > summary.peak_total_inflow:
                    summary.peak_total_inflow = v

            if flood_idx is not None:
                v = self._node_result(idx, flood_idx, p)
                if v > summary.peak_flooding:
                    summary.peak_flooding = v
                    summary.time_of_peak_flooding = self._period_time(p)

        return summary

    def link_summary(self, link_id: str, label: str = "") -> LinkSummary:
        """Get peak results summary for a link."""
        idx = self._link_id_to_idx.get(link_id)
        if idx is None:
            raise ElementNotFoundError("Link", link_id)

        prop_codes = self._link_prop_codes
        props = self._link_props[idx]
        link_type = int(props[list(prop_codes).index(0)]) if 0 in prop_codes else 0

        flow_idx = self._link_var_idx.get("flow_rate")
        depth_idx = self._link_var_idx.get("flow_depth")
        vel_idx = self._link_var_idx.get("flow_velocity")
        cap_idx = self._link_var_idx.get("capacity")

        summary = LinkSummary(
            guid=link_id,
            label=label or link_id,
            link_type=link_type,
        )

        for p in range(self._n_periods):
            if flow_idx is not None:
                v = self._link_result(idx, flow_idx, p)
                if abs(v) > abs(summary.peak_flow):
                    summary.peak_flow = v
                    summary.time_of_peak_flow = self._period_time(p)

            if depth_idx is not None:
                v = self._link_result(idx, depth_idx, p)
                if v > summary.peak_depth:
                    summary.peak_depth = v

            if vel_idx is not None:
                v = self._link_result(idx, vel_idx, p)
                if v > summary.peak_velocity:
                    summary.peak_velocity = v

            if cap_idx is not None:
                v = self._link_result(idx, cap_idx, p)
                if v > summary.max_capacity:
                    summary.max_capacity = v

        return summary

    def all_node_summaries(
        self, label_map: Optional[dict[str, str]] = None
    ) -> list[NodeSummary]:
        """Get peak summaries for all nodes."""
        label_map = label_map or {}
        return [
            self.node_summary(nid, label=label_map.get(nid, nid))
            for nid in self._node_ids
        ]

    def all_link_summaries(
        self, label_map: Optional[dict[str, str]] = None
    ) -> list[LinkSummary]:
        """Get peak summaries for all links."""
        label_map = label_map or {}
        return [
            self.link_summary(lid, label=label_map.get(lid, lid))
            for lid in self._link_ids
        ]

    def __repr__(self) -> str:
        return (
            f"ResultsReader('{self._path.name}', "
            f"nodes={self._n_nodes}, links={self._n_links}, "
            f"periods={self._n_periods}, interval={self._report_interval}s, "
            f"units={self.flow_units})"
        )


def find_results(iddx_path: str | Path) -> dict[str, list[Path]]:
    """Find all .out result files for an .iddx project.

    Returns a dict keyed by phase name, where each value is a list of
    .out file paths sorted by return period.
    """
    iddx_path = Path(iddx_path)
    project_name = iddx_path.stem
    results_dir = iddx_path.parent / project_name

    if not results_dir.is_dir():
        return {}

    results: dict[str, list[Path]] = {}
    for f in sorted(results_dir.glob("*.out")):
        parts = f.stem.rsplit("_", 2)
        if len(parts) >= 3:
            phase_name = parts[0]
        else:
            phase_name = f.stem
        results.setdefault(phase_name, []).append(f)

    return results


def load_results(
    iddx_path: str | Path, model=None
) -> dict[str, dict[float, ResultsReader]]:
    """Load all results for an .iddx project, organized by phase and return period.

    Args:
        iddx_path: Path to the .iddx file.
        model: Optional IddxModel to cross-reference labels.

    Returns:
        Nested dict: ``{phase_name: {return_period: ResultsReader}}``.
    """
    file_map = find_results(iddx_path)
    out: dict[str, dict[float, ResultsReader]] = {}

    for phase_name, paths in file_map.items():
        out[phase_name] = {}
        for p in paths:
            parts = p.stem.rsplit("_", 2)
            if len(parts) >= 3:
                try:
                    rp = float(parts[1])
                except ValueError:
                    rp = 0.0
            else:
                rp = 0.0
            out[phase_name][rp] = ResultsReader(p)

    return out


def build_label_map(model) -> dict[str, str]:
    """Build a GUID-to-label mapping from an IddxModel for readable results."""
    label_map: dict[str, str] = {}
    for _, phase in model.phases.items():
        for c in phase.catchments:
            label_map[c.guid] = c.label
        for j in phase.junctions:
            label_map[j.guid] = j.label
        for ds in phase.drainage_systems:
            label_map[ds.guid] = ds.label
        for conn in phase.connections:
            label_map[conn.guid] = conn.label
    return label_map


# ---- Cross-scenario comparison ----


@dataclass
class ScenarioResult:
    """Peak results extracted from a single scenario + return period."""

    scenario: str
    return_period: float
    node_peaks: dict[str, NodeSummary]
    link_peaks: dict[str, LinkSummary]
    system_peaks: dict[str, float]

    @property
    def max_flooding(self) -> float:
        return max((n.peak_flooding for n in self.node_peaks.values()), default=0.0)

    @property
    def max_flow(self) -> float:
        return max((abs(l.peak_flow) for l in self.link_peaks.values()), default=0.0)

    @property
    def max_velocity(self) -> float:
        return max((l.peak_velocity for l in self.link_peaks.values()), default=0.0)


class ScenarioComparison:
    """Compare results across multiple scenarios.

    Usage::

        comp = ScenarioComparison.from_iddx("path/to/project.iddx")
        comp.print_summary()
        comp.to_csv("comparison.csv")
    """

    def __init__(
        self, results: list[ScenarioResult], label_map: Optional[dict[str, str]] = None
    ):
        self.results = results
        self.label_map = label_map or {}

    @classmethod
    def from_iddx(cls, iddx_path: str | Path, model=None) -> "ScenarioComparison":
        """Load all results for a project and build comparison data."""
        from pathlib import Path as _Path

        iddx_path = _Path(iddx_path)

        if model is None:
            from .model import IddxModel

            model = IddxModel.open(iddx_path)

        lmap = build_label_map(model)
        file_map = find_results(iddx_path)
        results: list[ScenarioResult] = []

        for phase_name, paths in file_map.items():
            for p in paths:
                parts = p.stem.rsplit("_", 2)
                rp = 0.0
                if len(parts) >= 3:
                    try:
                        rp = float(parts[1])
                    except ValueError:
                        pass

                try:
                    reader = ResultsReader(p)
                except (ValueError, FileNotFoundError, ResultsError) as exc:
                    logger.warning("Skipping unreadable results file %s: %s", p, exc)
                    continue

                node_peaks = {}
                for nid in reader.node_ids:
                    node_peaks[nid] = reader.node_summary(nid, label=lmap.get(nid, nid))

                link_peaks = {}
                for lid in reader.link_ids:
                    link_peaks[lid] = reader.link_summary(lid, label=lmap.get(lid, lid))

                sys_peaks: dict[str, float] = {}
                for sv in reader.system_variables:
                    try:
                        ts = reader.system_time_series(sv)
                        sys_peaks[sv] = ts.peak
                    except KeyError as exc:
                        logger.debug("System variable not available in %s: %s", p, exc)

                results.append(
                    ScenarioResult(
                        scenario=phase_name,
                        return_period=rp,
                        node_peaks=node_peaks,
                        link_peaks=link_peaks,
                        system_peaks=sys_peaks,
                    )
                )

        return cls(results, label_map=lmap)

    def summary_table(self) -> list[dict]:
        """Build a list of dicts summarising each scenario -- one row per scenario+RP."""
        rows = []
        for r in self.results:
            row: dict = {
                "scenario": r.scenario,
                "return_period": r.return_period,
                "max_flooding": r.max_flooding,
                "max_flow": r.max_flow,
                "max_velocity": r.max_velocity,
                "peak_rainfall": r.system_peaks.get("rainfall", 0.0),
                "peak_runoff": r.system_peaks.get("runoff", 0.0),
                "peak_outfall_flow": r.system_peaks.get("outfall_flow", 0.0),
            }
            rows.append(row)
        return rows

    def node_comparison(self, variable: str = "peak_flooding") -> list[dict]:
        """Build a table comparing a node variable across all scenarios."""
        all_node_ids: list[str] = list(
            dict.fromkeys(nid for r in self.results for nid in r.node_peaks)
        )

        rows = []
        for nid in all_node_ids:
            row: dict = {"node_id": nid, "label": self.label_map.get(nid, nid)}
            for r in self.results:
                key = f"{r.scenario}_{r.return_period}"
                ns = r.node_peaks.get(nid)
                if ns is not None:
                    row[key] = getattr(ns, variable, 0.0)
                else:
                    row[key] = None
            rows.append(row)
        return rows

    def link_comparison(self, variable: str = "peak_flow") -> list[dict]:
        """Build a table comparing a link variable across all scenarios."""
        all_link_ids: list[str] = list(
            dict.fromkeys(lid for r in self.results for lid in r.link_peaks)
        )

        rows = []
        for lid in all_link_ids:
            row: dict = {"link_id": lid, "label": self.label_map.get(lid, lid)}
            for r in self.results:
                key = f"{r.scenario}_{r.return_period}"
                ls = r.link_peaks.get(lid)
                if ls is not None:
                    row[key] = getattr(ls, variable, 0.0)
                else:
                    row[key] = None
            rows.append(row)
        return rows

    @staticmethod
    def _write_csv(filepath: Path, table: list[dict]) -> Path:
        """Write rows to CSV, escaping any string cells against formula injection."""
        import csv

        if not table:
            return filepath

        fieldnames = list(table[0].keys())
        safe_rows = [
            {k: (_csv_safe(v) if isinstance(v, str) else v) for k, v in row.items()}
            for row in table
        ]
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(safe_rows)
        return filepath

    def to_csv(self, filepath: str | Path) -> Path:
        """Export summary comparison to CSV."""
        return self._write_csv(Path(filepath), self.summary_table())

    def nodes_to_csv(
        self, filepath: str | Path, variable: str = "peak_flooding"
    ) -> Path:
        """Export node-level comparison to CSV."""
        return self._write_csv(Path(filepath), self.node_comparison(variable))

    def links_to_csv(self, filepath: str | Path, variable: str = "peak_flow") -> Path:
        """Export link-level comparison to CSV."""
        return self._write_csv(Path(filepath), self.link_comparison(variable))

    def print_summary(self) -> None:
        """Print a formatted summary to the console."""
        table = self.summary_table()
        if not table:
            print("No results to compare.")
            return

        print(
            f"\n{'Scenario':<45s} {'RP':>6s} {'MaxFlood':>10s} {'MaxFlow':>10s} "
            f"{'MaxVel':>8s} {'Rainfall':>10s} {'Runoff':>10s} {'Outfall':>10s}"
        )
        print("-" * 110)
        for row in table:
            print(
                f"{row['scenario']:<45s} "
                f"{row['return_period']:>6.0f} "
                f"{row['max_flooding']:>10.4f} "
                f"{row['max_flow']:>10.4f} "
                f"{row['max_velocity']:>8.3f} "
                f"{row['peak_rainfall']:>10.4f} "
                f"{row['peak_runoff']:>10.4f} "
                f"{row['peak_outfall_flow']:>10.4f}"
            )
