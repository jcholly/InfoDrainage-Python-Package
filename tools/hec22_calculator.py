"""
HEC-22 Inlet Capacity Calculator
=================================
Pure-Python implementation of FHWA HEC-22 (3rd Edition) methodology for
computing gutter flow, spread, and inlet interception for on-grade and
in-sag storm drain inlets.

Reference: FHWA-NHI-10-009, Urban Drainage Design Manual (HEC-22), 2009.
All calculations use SI/metric units internally.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# Manning's equation coefficient for triangular gutter (SI)
KU = 0.376

# Side-flow interception coefficient (SI)
KU_SIDE = 0.0828

# Curb-opening required length coefficient (SI)
KU_CURB = 0.817

# m/ft conversion
M_PER_FT = 0.3048
FT_PER_M = 1.0 / M_PER_FT

# Splash-over velocity polynomial coefficients (US customary: L in ft, Vo in ft/s)
# From HEC-22 Chart 5 / Table 4-5
_SPLASH_OVER_COEFFS = {
    0: (2.218, 4.031, -0.649, 0.056),   # P-50
    1: (0.735, 2.437, -0.265, 0.018),   # P-50x100
    2: (1.762, 3.117, -0.451, 0.033),   # P-30
    3: (1.010, 3.224, -0.363, 0.030),   # Curved Vane
    4: (0.505, 2.344, -0.200, 0.014),   # 45-deg Tilt Bar
    5: (0.988, 2.625, -0.359, 0.029),   # 30-deg Tilt Bar
    6: (0.670, 2.454, -0.296, 0.029),   # Reticuline
}

GRATE_TYPE_NAMES = {
    0: "P-50",
    1: "P-50x100",
    2: "P-30",
    3: "Curved Vane",
    4: "45-deg Tilt Bar",
    5: "30-deg Tilt Bar",
    6: "Reticuline",
    7: "Generic",
}


@dataclass
class Hec22Result:
    """Results of an HEC-22 inlet capacity calculation."""
    approach_flow: float = 0.0       # Q total (m3/s)
    captured_flow: float = 0.0       # Qi intercepted (m3/s)
    bypass_flow: float = 0.0         # Qb = Q - Qi (m3/s)
    efficiency: float = 0.0          # E = Qi/Q
    spread: float = 0.0              # T, total spread (m)
    gutter_depth: float = 0.0        # d at curb face (m)
    velocity: float = 0.0            # average approach velocity (m/s)
    frontal_flow_ratio: float = 0.0  # Eo, fraction in gutter width
    splash_over_velocity: float = 0.0  # Vo (m/s)


# ── Gutter hydraulics ────────────────────────────────────────────────────

def gutter_flow(n: float, sx: float, sl: float, T: float) -> float:
    """Manning's equation for triangular gutter flow (SI).

    Args:
        n: Manning's roughness coefficient.
        sx: Cross slope (m/m), e.g. 0.02 for 2%.
        sl: Longitudinal slope (m/m).
        T: Spread width (m).

    Returns:
        Flow rate Q (m3/s).
    """
    if T <= 0 or sl <= 0 or sx <= 0:
        return 0.0
    return (KU / n) * sx ** (5.0 / 3.0) * sl ** 0.5 * T ** (8.0 / 3.0)


def spread_from_flow(Q: float, n: float, sx: float, sl: float) -> float:
    """Solve Manning's for spread T given flow Q (SI).

    Returns:
        Spread T (m).
    """
    if Q <= 0 or sl <= 0 or sx <= 0 or n <= 0:
        return 0.0
    denom = KU * sx ** (5.0 / 3.0) * sl ** 0.5
    if denom <= 0:
        return 0.0
    return (Q * n / denom) ** (3.0 / 8.0)


def composite_spread(Q: float, n: float, sx: float, sw: float,
                     W: float, sl: float, tol: float = 1e-6,
                     max_iter: int = 50) -> float:
    """Iterative spread calculation for composite (depressed) gutter.

    The gutter section has cross-slope sw over width W, and the road
    has cross-slope sx beyond the gutter.

    Args:
        Q: Total gutter flow (m3/s).
        n: Manning's roughness.
        sx: Road cross slope (m/m).
        sw: Gutter cross slope (m/m).
        W: Gutter width (m).
        sl: Longitudinal slope (m/m).

    Returns:
        Total spread T (m) from curb face.
    """
    if Q <= 0 or sl <= 0:
        return 0.0
    if abs(sw - sx) < 1e-9:
        return spread_from_flow(Q, n, sx, sl)

    T = spread_from_flow(Q, n, sx, sl)
    for _ in range(max_iter):
        if T <= W:
            Qs = 0.0
        else:
            Ts = T - W
            Qs = gutter_flow(n, sx, sl, Ts)
        Qw = Q - Qs
        if Qw <= 0:
            T = spread_from_flow(Q, n, sx, sl)
            break
        Tw = spread_from_flow(Qw, n, sw, sl)
        T_new = Tw + (T - W) if T > W else Tw
        Ts_new = T_new - W if T_new > W else 0.0
        Qs_new = gutter_flow(n, sx, sl, Ts_new) if Ts_new > 0 else 0.0
        T_new = W + spread_from_flow(max(0, Q - Qs_new), n, sw, sl) if Qs_new < Q else W
        if T_new <= W:
            T_new = spread_from_flow(Q, n, sw, sl)
        else:
            Ts2 = T_new - W
            Qs2 = gutter_flow(n, sx, sl, Ts2)
            Qw2 = Q - Qs2
            if Qw2 > 0:
                depth_at_gutter_edge = Ts2 * sx
                T_gutter = depth_at_gutter_edge / sw + W if sw > 0 else W
                T_new = max(T_new, Ts2 + W)

        if abs(T_new - T) < tol:
            T = T_new
            break
        T = T_new
    return max(T, 0.0)


def frontal_flow_ratio(T: float, W: float, sx: float, sw: float) -> float:
    """Eo: ratio of flow within the gutter width W to total flow.

    For uniform cross-slope (sx == sw), Eo = 1 - (1 - W/T)^(8/3).
    For composite gutter, uses the composite Eo formula from HEC-22 Eq 4-4.
    """
    if T <= 0:
        return 0.0
    if T <= W:
        return 1.0
    if abs(sw - sx) < 1e-9:
        return 1.0 - (1.0 - W / T) ** (8.0 / 3.0)
    ratio = sw / sx
    inner = (1.0 + (sw / sx) * (W / T)) ** (8.0 / 3.0) - 1.0
    if inner <= 0:
        return 0.0
    Eo = 1.0 / (1.0 + ratio / inner)
    return min(max(Eo, 0.0), 1.0)


def flow_velocity(Q: float, T: float, sx: float) -> float:
    """Average gutter flow velocity V = Q/A for triangular section."""
    if T <= 0 or sx <= 0:
        return 0.0
    A = 0.5 * T * T * sx
    if A <= 0:
        return 0.0
    return Q / A


# ── Splash-over velocity ────────────────────────────────────────────────

def splash_over_velocity(grate_type: int, grate_length_m: float) -> float:
    """Compute splash-over velocity Vo (m/s) for a given grate type and length.

    Uses polynomial coefficients from HEC-22 Table 4-5 (US customary),
    then converts to metric.
    """
    if grate_type not in _SPLASH_OVER_COEFFS:
        return 0.0

    L_ft = grate_length_m * FT_PER_M
    a, b, c, d = _SPLASH_OVER_COEFFS[grate_type]
    Vo_fps = a + b * L_ft + c * L_ft ** 2 + d * L_ft ** 3
    return max(Vo_fps * M_PER_FT, 0.0)


# ── Grate inlet on-grade ────────────────────────────────────────────────

def grate_interception_on_grade(
    Q: float, n: float, sx: float, sw: float, sl: float,
    W_gutter: float, L_grate: float, W_grate: float,
    grate_type: int, clogging_pct: float = 0.0,
    depression_m: float = 0.0,
) -> Hec22Result:
    """HEC-22 grate inlet interception on continuous grade.

    Args:
        Q: Approach flow (m3/s).
        n: Gutter Manning's n.
        sx: Road cross slope (m/m).
        sw: Gutter cross slope (m/m).
        sl: Longitudinal slope (m/m).
        W_gutter: Gutter width (m).
        L_grate: Grate length along curb (m).
        W_grate: Grate width perpendicular to curb (m).
        grate_type: SWMM5 grate type index (0-6).
        clogging_pct: Clogging factor (0-100).
        depression_m: Local depression depth (m).

    Returns:
        Hec22Result with all computed values.
    """
    if Q <= 0:
        return Hec22Result(approach_flow=0.0)

    T = spread_from_flow(Q, n, sx, sl) if abs(sw - sx) < 1e-9 else \
        composite_spread(Q, n, sx, sw, W_gutter, sl)

    Eo = frontal_flow_ratio(T, W_grate, sx, sw)
    V = flow_velocity(Q, T, sx)
    Vo = splash_over_velocity(grate_type, L_grate)

    # Frontal flow interception ratio
    if V <= Vo:
        Rf = 1.0
    else:
        Rf = max(0.0, 1.0 - 0.09 * (V - Vo))

    # Side flow interception ratio
    if V > 0 and L_grate > 0:
        Rs = 1.0 / (1.0 + KU_SIDE * V ** 1.8 / (sx * L_grate ** 2.3))
    else:
        Rs = 0.0

    Qi = Q * (Rf * Eo + Rs * (1.0 - Eo))
    Qi *= (1.0 - clogging_pct / 100.0)
    Qi = min(Qi, Q)

    d = T * sx

    return Hec22Result(
        approach_flow=Q,
        captured_flow=Qi,
        bypass_flow=Q - Qi,
        efficiency=Qi / Q if Q > 0 else 0.0,
        spread=T,
        gutter_depth=d,
        velocity=V,
        frontal_flow_ratio=Eo,
        splash_over_velocity=Vo,
    )


# ── Curb-opening inlet on-grade ─────────────────────────────────────────

def curb_interception_on_grade(
    Q: float, n: float, sx: float, sl: float,
    curb_length: float, clogging_pct: float = 0.0,
) -> Hec22Result:
    """HEC-22 curb-opening inlet interception on continuous grade.

    Args:
        Q: Approach flow (m3/s).
        n: Gutter Manning's n.
        sx: Road cross slope (m/m).
        sl: Longitudinal slope (m/m).
        curb_length: Curb opening length (m).
        clogging_pct: Clogging factor (0-100).

    Returns:
        Hec22Result.
    """
    if Q <= 0:
        return Hec22Result(approach_flow=0.0)

    T = spread_from_flow(Q, n, sx, sl)
    V = flow_velocity(Q, T, sx)

    # Required curb opening length for 100% interception (HEC-22 Eq 4-12)
    LT = KU_CURB * Q ** 0.42 * sl ** 0.3 * (1.0 / (n * sx)) ** 0.6

    if curb_length >= LT:
        E = 1.0
    else:
        E = 1.0 - (1.0 - curb_length / LT) ** 1.8

    Qi = E * Q * (1.0 - clogging_pct / 100.0)
    Qi = min(Qi, Q)
    d = T * sx

    return Hec22Result(
        approach_flow=Q,
        captured_flow=Qi,
        bypass_flow=Q - Qi,
        efficiency=Qi / Q if Q > 0 else 0.0,
        spread=T,
        gutter_depth=d,
        velocity=V,
    )


# ── Combination inlet on-grade ──────────────────────────────────────────

def combo_interception_on_grade(
    Q: float, n: float, sx: float, sw: float, sl: float,
    W_gutter: float, L_grate: float, W_grate: float,
    curb_length: float, grate_type: int,
    clogging_pct: float = 0.0, depression_m: float = 0.0,
) -> Hec22Result:
    """HEC-22 combination inlet (grate + curb) interception on continuous grade.

    Per HEC-22 Section 4.4.7: the grate intercepts its portion, then the
    curb opening captures additional flow from what the grate missed.
    """
    if Q <= 0:
        return Hec22Result(approach_flow=0.0)

    grate_result = grate_interception_on_grade(
        Q, n, sx, sw, sl, W_gutter, L_grate, W_grate,
        grate_type, clogging_pct, depression_m,
    )

    Qi_grate = grate_result.captured_flow
    Q_remaining = Q - Qi_grate

    if Q_remaining > 0 and curb_length > 0:
        curb_result = curb_interception_on_grade(
            Q_remaining, n, sx, sl, curb_length, clogging_pct,
        )
        Qi_curb = curb_result.captured_flow
    else:
        Qi_curb = 0.0

    Qi_total = Qi_grate + Qi_curb
    Qi_total = min(Qi_total, Q)

    return Hec22Result(
        approach_flow=Q,
        captured_flow=Qi_total,
        bypass_flow=Q - Qi_total,
        efficiency=Qi_total / Q if Q > 0 else 0.0,
        spread=grate_result.spread,
        gutter_depth=grate_result.gutter_depth,
        velocity=grate_result.velocity,
        frontal_flow_ratio=grate_result.frontal_flow_ratio,
        splash_over_velocity=grate_result.splash_over_velocity,
    )


# ── Slotted drain on-grade ──────────────────────────────────────────────

def slotted_interception_on_grade(
    Q: float, n: float, sx: float, sl: float,
    slot_length: float, clogging_pct: float = 0.0,
) -> Hec22Result:
    """HEC-22 slotted drain interception on continuous grade.

    Slotted drains behave similarly to curb openings for interception.
    """
    return curb_interception_on_grade(Q, n, sx, sl, slot_length, clogging_pct)


# ── In-sag calculations ─────────────────────────────────────────────────

def grate_interception_in_sag(
    Q: float, n: float, sx: float,
    L_grate: float, W_grate: float,
    clogging_pct: float = 0.0,
    perimeter_open: Optional[float] = None,
) -> Hec22Result:
    """HEC-22 grate inlet capacity in sag (weir/orifice control).

    In-sag inlets are controlled by either weir flow (shallow) or
    orifice flow (deep). This returns the lesser of the two.

    Args:
        Q: Approach flow (m3/s).
        perimeter_open: Open perimeter of grate for weir calc (m).
                       Defaults to 2*(L+W) with clogging reduction.
    """
    if Q <= 0:
        return Hec22Result(approach_flow=0.0)

    clog_factor = 1.0 - clogging_pct / 100.0
    A_clear = L_grate * W_grate * clog_factor
    if perimeter_open is None:
        perimeter_open = 2.0 * (L_grate + W_grate) * clog_factor

    # Weir equation: Q = Cw * P * d^1.5  (Cw ~ 1.66 SI)
    Cw = 1.66
    # Orifice equation: Q = Co * A * sqrt(2*g*d)  (Co ~ 0.67)
    Co = 0.67
    g = 9.81

    # Solve for depth d that produces flow Q under weir control
    if perimeter_open > 0:
        d_weir = (Q / (Cw * perimeter_open)) ** (2.0 / 3.0)
    else:
        d_weir = float("inf")

    # Solve for depth d under orifice control
    if A_clear > 0:
        d_orifice = (Q / (Co * A_clear)) ** 2 / (2.0 * g)
    else:
        d_orifice = float("inf")

    d = max(d_weir, d_orifice)

    Qi = min(Q, Q)

    return Hec22Result(
        approach_flow=Q,
        captured_flow=Qi,
        bypass_flow=0.0,
        efficiency=1.0,
        spread=0.0,
        gutter_depth=d,
    )


# ── High-level sizing function ──────────────────────────────────────────

def size_inlet(
    approach_flow: float,
    inlet_type: int,
    gutter_slope_1x: float,
    road_x_slope_1x: float,
    gutter_x_slope_1x: float,
    gutter_width: float,
    mannings_n: float,
    location: int = 0,
    grate_length: float = 0.0,
    grate_width: float = 0.0,
    grate_type: int = 3,
    curb_length: float = 0.0,
    curb_height: float = 0.0,
    slot_length: float = 0.0,
    slot_width: float = 0.0,
    depression_mm: float = 0.0,
    clogging_pct: float = 0.0,
) -> Hec22Result:
    """Size an inlet using HEC-22 methodology.

    All slope values are in InfoDrainage 1:X format (e.g. 50 means 1:50 = 0.02).

    Args:
        approach_flow: Total approach flow to inlet (m3/s).
        inlet_type: 0=Grate, 1=Curb, 2=Combo, 3=Slotted.
        gutter_slope_1x: Longitudinal slope as 1:X.
        road_x_slope_1x: Road cross slope as 1:X.
        gutter_x_slope_1x: Gutter cross slope as 1:X.
        gutter_width: Gutter width (m).
        mannings_n: Gutter Manning's n.
        location: 0=On-Grade, 1=In-Sag.
        grate_length: Grate length along curb (m).
        grate_width: Grate width perpendicular to curb (m).
        grate_type: SWMM5 grate type index (0-7).
        curb_length: Curb opening length (m).
        curb_height: Curb opening height (m).
        slot_length: Slotted drain length (m).
        slot_width: Slot width (m).
        depression_mm: Local gutter depression (mm).
        clogging_pct: Clogging factor (0-100).

    Returns:
        Hec22Result with computed flows, spread, velocity, efficiency.
    """
    sl = 1.0 / gutter_slope_1x if gutter_slope_1x > 0 else 0.0
    sx = 1.0 / road_x_slope_1x if road_x_slope_1x > 0 else 0.0
    sw = 1.0 / gutter_x_slope_1x if gutter_x_slope_1x > 0 else sx
    dep_m = depression_mm / 1000.0
    Q = approach_flow

    if location == 1:  # In-sag
        if inlet_type in (0, 2):  # Grate or Combo
            return grate_interception_in_sag(
                Q, mannings_n, sx, grate_length, grate_width,
                clogging_pct,
            )
        else:
            return Hec22Result(approach_flow=Q, captured_flow=Q, efficiency=1.0)

    # On-grade
    if inlet_type == 0:  # Grate
        return grate_interception_on_grade(
            Q, mannings_n, sx, sw, sl, gutter_width,
            grate_length, grate_width, grate_type, clogging_pct, dep_m,
        )
    elif inlet_type == 1:  # Curb
        return curb_interception_on_grade(
            Q, mannings_n, sx, sl, curb_length, clogging_pct,
        )
    elif inlet_type == 2:  # Combo
        return combo_interception_on_grade(
            Q, mannings_n, sx, sw, sl, gutter_width,
            grate_length, grate_width, curb_length, grate_type,
            clogging_pct, dep_m,
        )
    elif inlet_type == 3:  # Slotted
        return slotted_interception_on_grade(
            Q, mannings_n, sx, sl, slot_length, clogging_pct,
        )
    else:
        return Hec22Result(approach_flow=Q)


def size_inlet_from_iddx(inlet_detail, approach_flow: float) -> Hec22Result:
    """Size an inlet using its iddx_core InletDetail configuration.

    Convenience wrapper that extracts all parameters from the InletDetail's
    Hec22InletConfig and calls size_inlet().
    """
    cfg = inlet_detail.hec22_config
    if cfg is None:
        return Hec22Result(approach_flow=approach_flow)

    gutter = cfg.gutter
    if gutter is None:
        return Hec22Result(approach_flow=approach_flow)

    p = cfg.inlet_params
    kwargs = {
        "approach_flow": approach_flow,
        "inlet_type": cfg.hec22_inlet_type,
        "gutter_slope_1x": gutter.slope,
        "road_x_slope_1x": gutter.road_x_slope,
        "gutter_x_slope_1x": gutter.gutter_x_slope,
        "gutter_width": gutter.width,
        "mannings_n": gutter.mannings_n,
        "location": getattr(p, "location", 0) if p else 0,
        "depression_mm": getattr(p, "depression", 0.0) if p else 0.0,
        "clogging_pct": getattr(p, "clogging", 0.0) if p else 0.0,
    }

    if p:
        if hasattr(p, "grate_length"):
            kwargs["grate_length"] = p.grate_length
        if hasattr(p, "width"):
            kwargs["grate_width"] = p.width
        if hasattr(p, "grate_type_swmm5"):
            kwargs["grate_type"] = p.grate_type_swmm5
        if hasattr(p, "curb_length"):
            kwargs["curb_length"] = p.curb_length
        if hasattr(p, "curb_height"):
            kwargs["curb_height"] = getattr(p, "height", 0.0)
        if hasattr(p, "slot_length"):
            kwargs["slot_length"] = p.slot_length
            kwargs["slot_width"] = getattr(p, "width", 0.0)

    return size_inlet(**kwargs)
