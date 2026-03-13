"""Node classes: Catchments, Junctions, and Drainage Systems (SWCs)."""

from __future__ import annotations
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element
from typing import Optional

from .enums import (
    RunoffMethod, JunctionType, JunctionShape, OutletType,
    DrainageSystemType, ELEMENT_TO_DSYS_TYPE, DRAINAGE_SYSTEM_ELEMENTS,
    ALL_DSYS_TAGS, IAType, ToCMethod,
)
from .utils import (
    get_float, get_int, get_bool, get_str, set_float, set_int, set_bool,
    new_guid, parse_coordinate_2d, make_coordinate_2d,
    parse_polygon, make_polygon_element, find_or_create,
)


def _safe_runoff_method(value: int) -> RunoffMethod:
    try:
        return RunoffMethod(value)
    except ValueError:
        return RunoffMethod.RATIONAL


# ---------------------------------------------------------------------------
# Catchment (AreaInflowNode)
# ---------------------------------------------------------------------------

@dataclass
class ToCDetails:
    """Time of Concentration calculation parameters."""
    area: float = 0.0
    slope: float = 0.0
    length: float = 0.0
    runoff_coefficient: float = 0.75
    tc: float = 300.0
    pimp: int = 100
    urban_creep: float = 0.0
    toc_method: int = 0
    toc_flag_calc: bool = False
    roughness: float = 0.0

    @classmethod
    def from_xml(cls, elem: Element) -> ToCDetails:
        obj = cls(
            area=get_float(elem, "Area"),
            slope=get_float(elem, "Slope"),
            length=get_float(elem, "Length"),
            runoff_coefficient=get_float(elem, "RunoffCoefficient", 0.75),
            tc=get_float(elem, "TC", 300),
            pimp=get_int(elem, "PIMP", 100),
            urban_creep=get_float(elem, "UrbanCreep"),
        )
        toc_calc = elem.find("ToCCalculator")
        if toc_calc is not None:
            obj.toc_method = get_int(toc_calc, "ToCMethod")
            obj.toc_flag_calc = get_bool(toc_calc, "FlagCalc")
            friend = toc_calc.find("FriendEquationToCDetails")
            if friend is not None:
                obj.roughness = get_float(friend, "Roughness")
        return obj

    def to_xml(self) -> Element:
        elem = Element("TCDetails")
        set_float(elem, "Area", self.area)
        set_float(elem, "Slope", self.slope)
        set_float(elem, "Length", self.length)
        set_float(elem, "RunoffCoefficient", self.runoff_coefficient)
        set_float(elem, "TC", self.tc)
        set_int(elem, "PIMP", self.pimp)
        set_float(elem, "UrbanCreep", self.urban_creep)
        toc = Element("ToCCalculator")
        set_int(toc, "ToCMethod", self.toc_method)
        set_bool(toc, "FlagCalc", self.toc_flag_calc)
        set_float(toc, "TC", self.tc)
        set_float(toc, "Area", self.area if self.toc_flag_calc else 0.0)
        set_float(toc, "Slope", self.slope if self.toc_flag_calc else 0.0)
        set_float(toc, "Length", self.length if self.toc_flag_calc else 0.0)
        set_float(toc, "RunoffCoefficient", self.runoff_coefficient if self.toc_flag_calc else 0.0)
        friend = Element("FriendEquationToCDetails")
        set_float(friend, "Roughness", self.roughness)
        set_float(friend, "Length", self.length if self.toc_flag_calc else 0.0)
        set_float(friend, "Slope", self.slope if self.toc_flag_calc else 0.0)
        toc.append(friend)
        elem.append(toc)
        return elem


@dataclass
class SCSDetails:
    """SCS Curve Number method parameters."""
    area: float = 0.0
    slope: float = 0.0
    length: float = 0.0
    runoff_coefficient: float = 0.25
    pervious_cn: int = 65
    pervious_cn_user: bool = True
    tc: float = 300.0
    shape_factor: int = 484
    shape_type: int = 0
    init_abs_depth: float = 0.0
    init_abs_fraction: float = 0.2
    ia_type: int = 1
    pimp: int = 20
    pimp_user: bool = True
    urban_creep: float = 0.0
    composite_cn: float = 0.0
    toc_method: int = 0
    toc_flag_calc: bool = False
    roughness: float = 0.0
    cn_land_use: int = 0
    cn_cover_type: int = 0
    cn_condition: int = 0
    cn_soil_group: int = 0

    @classmethod
    def from_xml(cls, elem: Element) -> SCSDetails:
        obj = cls(
            area=get_float(elem, "Area"),
            slope=get_float(elem, "Slope"),
            length=get_float(elem, "Length"),
            runoff_coefficient=get_float(elem, "RunoffCoefficient", 0.25),
            pervious_cn=get_int(elem, "PACN", 65),
            pervious_cn_user=get_bool(elem, "PACN_User"),
            tc=get_float(elem, "TC", 300),
            shape_factor=get_int(elem, "ShapeFactor", 484),
            shape_type=get_int(elem, "ShapeType"),
            init_abs_depth=get_float(elem, "InitAbsDepth"),
            init_abs_fraction=get_float(elem, "InitAbsFraction", 0.2),
            ia_type=get_int(elem, "IAType", 1),
            pimp=get_int(elem, "PIMP", 20),
            pimp_user=get_bool(elem, "PIMP_User"),
            urban_creep=get_float(elem, "UrbanCreep"),
            composite_cn=get_float(elem, "CompositeCN"),
        )
        toc_calc = elem.find("ToCCalculator")
        if toc_calc is not None:
            obj.toc_method = get_int(toc_calc, "ToCMethod")
            obj.toc_flag_calc = get_bool(toc_calc, "FlagCalc")
            friend = toc_calc.find("FriendEquationToCDetails")
            if friend is not None:
                obj.roughness = get_float(friend, "Roughness")
        cn_det = elem.find("CNCalcDetails")
        if cn_det is not None:
            obj.cn_land_use = get_int(cn_det, "LandUse")
            obj.cn_cover_type = get_int(cn_det, "CoverType")
            obj.cn_condition = get_int(cn_det, "Condition")
            obj.cn_soil_group = get_int(cn_det, "SoilGroup")
        return obj

    def to_xml(self) -> Element:
        elem = Element("SCSDet")
        set_float(elem, "Area", self.area)
        set_float(elem, "Slope", self.slope)
        set_float(elem, "Length", self.length)
        set_float(elem, "RunoffCoefficient", self.runoff_coefficient)
        set_int(elem, "PACN", self.pervious_cn)
        set_bool(elem, "PACN_User", self.pervious_cn_user)
        set_float(elem, "TC", self.tc)
        set_int(elem, "ShapeFactor", self.shape_factor)
        set_int(elem, "ShapeType", self.shape_type)
        set_float(elem, "InitAbsDepth", self.init_abs_depth)
        set_float(elem, "InitAbsFraction", self.init_abs_fraction)
        set_int(elem, "IAType", self.ia_type)
        set_int(elem, "PIMP", self.pimp)
        set_bool(elem, "PIMP_User", self.pimp_user)
        set_float(elem, "UrbanCreep", self.urban_creep)
        set_float(elem, "CompositeCN", self.composite_cn)
        toc = Element("ToCCalculator")
        set_int(toc, "ToCMethod", self.toc_method)
        set_bool(toc, "FlagCalc", self.toc_flag_calc)
        set_float(toc, "TC", self.tc)
        set_float(toc, "Area", self.area if self.toc_flag_calc else 0.0)
        set_float(toc, "Slope", self.slope if self.toc_flag_calc else 0.0)
        set_float(toc, "Length", self.length if self.toc_flag_calc else 0.0)
        set_float(toc, "RunoffCoefficient", self.runoff_coefficient if self.toc_flag_calc else 0.0)
        friend = Element("FriendEquationToCDetails")
        set_float(friend, "Roughness", self.roughness)
        set_float(friend, "Length", self.length if self.toc_flag_calc else 0.0)
        set_float(friend, "Slope", self.slope if self.toc_flag_calc else 0.0)
        toc.append(friend)
        elem.append(toc)
        cn = Element("CNCalcDetails")
        set_int(cn, "CurveNo", 0)
        set_int(cn, "LandUse", self.cn_land_use)
        set_int(cn, "CoverType", self.cn_cover_type)
        set_int(cn, "Condition", self.cn_condition)
        set_int(cn, "SoilGroup", self.cn_soil_group)
        elem.append(cn)
        return elem


@dataclass
class Catchment:
    """Represents an AreaInflowNode (catchment/inflow area)."""
    index: int = 0
    label: str = ""
    guid: str = field(default_factory=new_guid)
    x: float = 0.0
    y: float = 0.0
    cv: float = 0.75
    cv_user: bool = True
    cvps: float = 0.75
    cvps_user: bool = False
    cv_winter: float = 0.84
    runoff_method: RunoffMethod = RunoffMethod.RATIONAL
    area: float = 0.0
    pimp: int = 100
    pimp_user: bool = False
    tcps: float = 300.0
    use_land_uses: bool = False
    auto_wqv: bool = True
    to_dest_guid: str = ""
    to_dest_label: str = ""
    boundary: list[tuple[float, float]] = field(default_factory=list)
    toc_details: Optional[ToCDetails] = None
    scs_details: Optional[SCSDetails] = None
    _raw_element: Optional[Element] = field(default=None, repr=False)

    @property
    def area_acres(self) -> float:
        return self.area * 640.0

    @property
    def area_sq_ft(self) -> float:
        return self.area * 27_878_400.0

    @classmethod
    def from_xml(cls, elem: Element) -> Catchment:
        coord = elem.find("Coordinate2D")
        x, y = parse_coordinate_2d(coord) if coord is not None else (0.0, 0.0)

        to_dest = elem.find("ToDest")
        to_guid = get_str(to_dest, "ftGUID") if to_dest is not None else ""
        to_label = get_str(to_dest, "ToLabel") if to_dest is not None else ""

        outline = elem.find("FreeFormOutlineDetails")
        boundary = parse_polygon(outline) if outline is not None else []

        toc_det = None
        tc_elem = elem.find("TCDetails")
        if tc_elem is not None:
            toc_det = ToCDetails.from_xml(tc_elem)

        scs_det = None
        scs_elem = elem.find("SCSDet")
        if scs_elem is not None:
            scs_det = SCSDetails.from_xml(scs_elem)

        return cls(
            index=get_int(elem, "Index"),
            label=get_str(elem, "Label"),
            guid=get_str(elem, "GUID", new_guid()),
            x=x, y=y,
            cv=get_float(elem, "CV", 0.75),
            cv_user=get_bool(elem, "CV_User"),
            cvps=get_float(elem, "CVPS", 0.75),
            cvps_user=get_bool(elem, "CVPS_User"),
            cv_winter=get_float(elem, "CVWint", 0.84),
            runoff_method=_safe_runoff_method(get_int(elem, "RunoffMethod", 0)),
            area=get_float(elem, "Area"),
            pimp=get_int(elem, "PrelimPercImpervious", 100),
            pimp_user=get_bool(elem, "PrelimPercImpervious_User"),
            tcps=get_float(elem, "TCPS", 300),
            use_land_uses=get_bool(elem, "UseLandUses"),
            auto_wqv=get_bool(elem, "ATWQv", True),
            to_dest_guid=to_guid,
            to_dest_label=to_label,
            boundary=boundary,
            toc_details=toc_det,
            scs_details=scs_det,
            _raw_element=elem,
        )

    def to_xml(self, index: Optional[int] = None) -> Element:
        import copy as _copy
        idx = index if index is not None else self.index

        if self._raw_element is not None:
            elem = _copy.deepcopy(self._raw_element)
            set_int(elem, "Index", idx)
            elem.set("Label", self.label)
            elem.set("GUID", self.guid)
            set_float(elem, "CV", self.cv)
            set_bool(elem, "CV_User", self.cv_user)
            set_float(elem, "CVPS", self.cvps)
            set_bool(elem, "CVPS_User", self.cvps_user)
            set_float(elem, "CVWint", self.cv_winter)
            set_float(elem, "TCPS", self.tcps)
            set_float(elem, "Area", self.area)
            set_int(elem, "PrelimPercImpervious", self.pimp)
            if self.pimp_user:
                set_bool(elem, "PrelimPercImpervious_User", True)
            set_int(elem, "RunoffMethod", self.runoff_method.value)
            set_bool(elem, "UseLandUses", self.use_land_uses)
            set_bool(elem, "ATWQv", self.auto_wqv)

            to_dest = elem.find("ToDest")
            if to_dest is not None:
                if self.to_dest_guid:
                    to_dest.set("ftGUID", self.to_dest_guid)
                to_dest.set("ToLabel", self.to_dest_label)

            if self.toc_details is not None:
                old_tc = elem.find("TCDetails")
                if old_tc is not None:
                    tc_idx = list(elem).index(old_tc)
                    elem.remove(old_tc)
                    elem.insert(tc_idx, self.toc_details.to_xml())

            if self.scs_details is not None:
                old_scs = elem.find("SCSDet")
                if old_scs is not None:
                    scs_idx = list(elem).index(old_scs)
                    elem.remove(old_scs)
                    elem.insert(scs_idx, self.scs_details.to_xml())

            return elem

        elem = Element("AreaInflowNode")
        set_int(elem, "Index", idx)
        elem.set("Label", self.label)
        elem.set("IcoIndex", "1")
        set_float(elem, "CVPS", self.cvps)
        if self.cvps_user:
            set_bool(elem, "CVPS_User", True)
        set_float(elem, "TCPS", self.tcps)
        set_float(elem, "CV", self.cv)
        set_bool(elem, "CV_User", self.cv_user)
        set_float(elem, "CVWint", self.cv_winter)
        set_int(elem, "RunoffMethod", self.runoff_method.value)
        set_float(elem, "Area", self.area)
        set_bool(elem, "UseLandUses", self.use_land_uses)
        set_bool(elem, "ReqLandUseCalcs", False)
        set_int(elem, "PrelimPercImpervious", self.pimp)
        if self.pimp_user:
            set_bool(elem, "PrelimPercImpervious_User", True)
        set_bool(elem, "ATWQv", self.auto_wqv)
        set_int(elem, "OutlineType", 0)
        set_float(elem, "CS", 0)
        set_float(elem, "RPL", 0)
        elem.set("GUID", self.guid)

        elem.append(make_coordinate_2d(self.x, self.y))
        elem.append(Element("PollConcs"))

        tank = Element("RainwaterTank")
        set_int(tank, "Tanks", 1)
        set_bool(tank, "Used", False)
        det = Element("Det")
        set_bool(det, "Used", False)
        for a in ("Volume", "Height", "Width", "Length", "InitPerc", "TankType", "OutflowSF"):
            set_int(det, a, 0)
        tank.append(det)
        ret = Element("Ret")
        set_bool(ret, "Used", False)
        for a in ("Volume", "Height", "Width", "Length", "InitPerc", "TankType", "OutflowMF"):
            set_int(ret, a, 0)
        tank.append(ret)
        elem.append(tank)

        to_dest = Element("ToDest")
        if self.to_dest_guid:
            to_dest.set("ftGUID", self.to_dest_guid)
        to_dest.set("ToLabel", self.to_dest_label)
        elem.append(to_dest)

        if self.runoff_method == RunoffMethod.SCS_CURVE_NUMBER and self.scs_details:
            elem.append(self.scs_details.to_xml())
        elif self.toc_details:
            elem.append(self.toc_details.to_xml())
        else:
            toc = ToCDetails(
                area=self.area, tc=self.tcps, pimp=self.pimp,
                runoff_coefficient=self.cv,
            )
            elem.append(toc.to_xml())

        standalone_toc = Element("ToCCalculator")
        set_int(standalone_toc, "ToCMethod", 0)
        set_bool(standalone_toc, "FlagCalc", False)
        set_float(standalone_toc, "TC", 300)
        for a in ("Area", "Slope", "Length", "RunoffCoefficient"):
            set_float(standalone_toc, a, 0)
        fr = Element("FriendEquationToCDetails")
        for a in ("Roughness", "Length", "Slope"):
            set_float(fr, a, 0)
        standalone_toc.append(fr)
        elem.append(standalone_toc)

        if self.boundary:
            elem.append(make_polygon_element(self.boundary))
        else:
            outline = Element("FreeFormOutlineDetails")
            set_bool(outline, "CentreLineLocked", False)
            outline.append(Element("CentreLine"))
            outline.append(Element("Coord2Ds"))
            outline.append(Element("BaseCoords"))
            elem.append(outline)

        cv_calc = Element("CVCalculatorDetails")
        for a in ("CVLandUses", "CVOverlandSlope", "RunoffCoefficient"):
            set_int(cv_calc, a, 0)
        elem.append(cv_calc)
        return elem


# ---------------------------------------------------------------------------
# Junction
# ---------------------------------------------------------------------------

@dataclass
class InletSource:
    """A source feeding into a junction inlet."""
    guid: str = ""
    label: str = ""


@dataclass
class InletDetail:
    """An inlet on a junction."""
    index: int = 0
    label: str = "Inlet"
    guid: str = field(default_factory=new_guid)
    parent_guid: str = ""
    sources: list[InletSource] = field(default_factory=list)


@dataclass
class OutletDetail:
    """An outlet on a junction or drainage system."""
    index: int = 0
    label: str = "Outlet"
    guid: str = field(default_factory=new_guid)
    parent_guid: str = ""
    outlet_type: OutletType = OutletType.FLOW_CONTROL
    il: float = 0.0
    design_depth: float = 0.0
    design_flow: float = 0.0
    to_dest_guid: str = ""
    to_dest_label: str = ""
    orifice_diameter: float = 0.0
    orifice_cdo: float = 0.6
    weir_width: float = 0.0
    weir_cdw: float = 0.544
    flow_control_guid: str = field(default_factory=new_guid)

    @classmethod
    def from_xml(cls, elem: Element) -> OutletDetail:
        type_int = get_int(elem, "Type", 0)
        try:
            otype = OutletType(type_int)
        except ValueError:
            otype = OutletType.FLOW_CONTROL

        obj = cls(
            index=get_int(elem, "Index"),
            label=get_str(elem, "Label", "Outlet"),
            guid=get_str(elem, "GUID", new_guid()),
            parent_guid=get_str(elem, "ftGUID"),
            outlet_type=otype,
        )
        to_dest = elem.find("ToDest")
        if to_dest is not None:
            obj.to_dest_guid = get_str(to_dest, "ftGUID")
            obj.to_dest_label = get_str(to_dest, "ToLabel")

        if otype in (OutletType.FLOW_CONTROL, OutletType.FREE_OUTLET):
            fc = elem.find("FlowControl")
            if fc is not None:
                obj.il = get_float(fc, "IL")
                obj.design_depth = get_float(fc, "DesignDepth")
                obj.design_flow = get_float(fc, "DesignFlow")
                obj.flow_control_guid = get_str(fc, "GUID", new_guid())
        elif otype == OutletType.ORIFICE:
            ori = elem.find("CtrlOrifice")
            if ori is not None:
                obj.il = get_float(ori, "IL")
                obj.design_depth = get_float(ori, "DesignDepth")
                obj.design_flow = get_float(ori, "DesignFlow")
                obj.orifice_diameter = get_float(ori, "DiamDepth")
                obj.orifice_cdo = get_float(ori, "CDO", 0.6)
                obj.flow_control_guid = get_str(ori, "GUID", new_guid())
        elif otype == OutletType.WEIR:
            weir = elem.find("CtrlWeir")
            if weir is not None:
                obj.il = get_float(weir, "IL")
                obj.design_depth = get_float(weir, "DesignDepth")
                obj.design_flow = get_float(weir, "DesignFlow")
                obj.weir_width = get_float(weir, "Width")
                obj.weir_cdw = get_float(weir, "CDW", 0.544)
                obj.flow_control_guid = get_str(weir, "GUID", new_guid())
        elif otype == OutletType.COMPLEX:
            cc = elem.find("ComplexCtrl")
            if cc is not None:
                obj.il = get_float(cc, "IL")
                obj.design_depth = get_float(cc, "DesignDepth")
                obj.design_flow = get_float(cc, "DesignFlow")
                obj.flow_control_guid = get_str(cc, "GUID", new_guid())
                fcs = cc.find("FlowControls")
                if fcs is not None:
                    ori = fcs.find("CtrlOrifice")
                    if ori is not None:
                        obj.orifice_diameter = get_float(ori, "DiamDepth")
                        obj.orifice_cdo = get_float(ori, "CDO", get_float(ori, "CD", 0.6))
                    weir = fcs.find("CtrlWeir")
                    if weir is not None:
                        obj.weir_width = get_float(weir, "Width")
                        obj.weir_cdw = get_float(weir, "CDW", get_float(weir, "CD", 0.544))
        elif otype == OutletType.PUMP:
            pump = elem.find("CtrlPump")
            if pump is not None:
                obj.il = get_float(pump, "IL")
                obj.design_depth = get_float(pump, "DesignDepth")
                obj.design_flow = get_float(pump, "DesignFlow")
                obj.flow_control_guid = get_str(pump, "GUID", new_guid())
        return obj

    def to_xml(self) -> Element:
        elem = Element("ODetail")
        set_int(elem, "Index", self.index)
        elem.set("Label", self.label)
        elem.set("ftGUID", self.parent_guid)
        set_int(elem, "Type", self.outlet_type.value)
        elem.set("GUID", self.guid)

        if self.outlet_type == OutletType.FLOW_CONTROL:
            fc = Element("FlowControl")
            set_float(fc, "IL", self.il)
            set_float(fc, "DesignDepth", self.design_depth)
            set_float(fc, "DesignFlow", self.design_flow)
            set_float(fc, "DesiredDesignDepth", 0)
            set_float(fc, "DesiredDesignFlow", 0)
            fc.set("GUID", self.flow_control_guid)
            elem.append(fc)
        elif self.outlet_type == OutletType.ORIFICE:
            coord = make_coordinate_2d(0, 0)
            elem.append(coord)
            ori = Element("CtrlOrifice")
            set_float(ori, "IL", self.il)
            set_bool(ori, "IL_User", True)
            set_float(ori, "DesignDepth", self.design_depth)
            set_float(ori, "DesignFlow", self.design_flow)
            set_float(ori, "DesiredDesignDepth", 0)
            set_float(ori, "DesiredDesignFlow", 0)
            set_float(ori, "DiamDepth", self.orifice_diameter)
            set_float(ori, "CDO", self.orifice_cdo)
            ori.set("GUID", self.flow_control_guid)
            elem.append(ori)
        elif self.outlet_type == OutletType.WEIR:
            coord = make_coordinate_2d(0, 0)
            elem.append(coord)
            weir = Element("CtrlWeir")
            set_float(weir, "IL", self.il)
            set_bool(weir, "IL_User", True)
            set_float(weir, "DesignDepth", self.design_depth)
            set_float(weir, "DesignFlow", self.design_flow)
            set_float(weir, "DesiredDesignDepth", 0)
            set_float(weir, "DesiredDesignFlow", 0)
            set_float(weir, "CDW", self.weir_cdw)
            set_float(weir, "Width", self.weir_width)
            set_bool(weir, "Width_User", True)
            weir.set("GUID", self.flow_control_guid)
            elem.append(weir)

        to_dest = Element("ToDest")
        if self.to_dest_guid:
            to_dest.set("ftGUID", self.to_dest_guid)
        to_dest.set("ToLabel", self.to_dest_label)
        elem.append(to_dest)
        return elem


@dataclass
class Junction:
    """Represents a junction node (manhole, inlet structure, outfall)."""
    index: int = 0
    label: str = ""
    guid: str = field(default_factory=new_guid)
    x: float = 0.0
    y: float = 0.0
    is_outfall: bool = False
    junction_type: JunctionType = JunctionType.STRUCTURE
    shape: JunctionShape = JunctionShape.CIRCULAR
    diameter: float = 0.6096
    width: float = 0.0
    length: float = 0.0
    cover_level: float = 0.0
    invert_level: float = 0.0
    depth: float = 0.0
    sump_depth: float = 0.0
    sealed: bool = False
    part_family: int = 0
    bend_loss: float = 0.0
    inlets: list[InletDetail] = field(default_factory=list)
    outlets: list[OutletDetail] = field(default_factory=list)
    _raw_element: Optional[Element] = field(default=None, repr=False)

    @classmethod
    def from_xml(cls, elem: Element) -> Junction:
        coord = elem.find("Coordinate2D")
        x, y = parse_coordinate_2d(coord) if coord is not None else (0.0, 0.0)

        inlets = []
        inlet_dets = elem.find("InletDetails")
        if inlet_dets is not None:
            for idet in inlet_dets.findall("IDetail"):
                sources = []
                guids_elem = idet.find("GUIDS")
                if guids_elem is not None:
                    for fs in guids_elem.findall("FromSource"):
                        sources.append(InletSource(
                            guid=get_str(fs, "ftGUID"),
                            label=get_str(fs, "FromLabel"),
                        ))
                inlets.append(InletDetail(
                    index=get_int(idet, "Index"),
                    label=get_str(idet, "Label", "Inlet"),
                    guid=get_str(idet, "GUID", new_guid()),
                    parent_guid=get_str(idet, "ftGUID"),
                    sources=sources,
                ))

        outlets = []
        outlet_dets = elem.find("OutletDetails")
        if outlet_dets is not None:
            for odet in outlet_dets.findall("ODetail"):
                outlets.append(OutletDetail.from_xml(odet))

        return cls(
            index=get_int(elem, "Index"),
            label=get_str(elem, "Label"),
            guid=get_str(elem, "GUID", new_guid()),
            x=x, y=y,
            is_outfall=get_bool(elem, "IsOut"),
            junction_type=JunctionType(get_int(elem, "Type", 1)),
            shape=JunctionShape(get_int(elem, "Shape", 0)),
            diameter=get_float(elem, "Diameter", 0.6096),
            width=get_float(elem, "Width"),
            length=get_float(elem, "Length"),
            cover_level=get_float(elem, "CL"),
            invert_level=get_float(elem, "IL"),
            depth=get_float(elem, "Depth"),
            sump_depth=get_float(elem, "SumpDepth"),
            sealed=get_bool(elem, "Sealed"),
            part_family=get_int(elem, "PartFamily"),
            bend_loss=get_float(elem, "BendLoss"),
            inlets=inlets,
            outlets=outlets,
            _raw_element=elem,
        )

    def to_xml(self, index: Optional[int] = None) -> Element:
        import copy as _copy
        idx = index if index is not None else self.index

        if self._raw_element is not None:
            elem = _copy.deepcopy(self._raw_element)
            set_int(elem, "Index", idx)
            elem.set("Label", self.label)
            elem.set("GUID", self.guid)
            set_bool(elem, "IsOut", self.is_outfall)
            set_int(elem, "Type", self.junction_type.value)
            set_int(elem, "Shape", self.shape.value)
            set_float(elem, "CL", self.cover_level)
            set_float(elem, "IL", self.invert_level)
            set_float(elem, "Depth", self.depth)
            set_float(elem, "Diameter", self.diameter)
            set_float(elem, "Width", self.width)
            set_float(elem, "Length", self.length)
            set_float(elem, "SumpDepth", self.sump_depth)
            set_bool(elem, "Sealed", self.sealed)
            set_float(elem, "BendLoss", self.bend_loss)
            set_int(elem, "PartFamily", self.part_family)

            outlet_dets = elem.find("OutletDetails")
            if outlet_dets is not None:
                for odet_elem in outlet_dets.findall("ODetail"):
                    odet_guid = get_str(odet_elem, "GUID")
                    matched = next(
                        (o for o in self.outlets if o.guid == odet_guid), None
                    )
                    if matched is None:
                        continue
                    otype = get_int(odet_elem, "Type", 0)
                    if otype == OutletType.ORIFICE.value:
                        ori = odet_elem.find("CtrlOrifice")
                        if ori is not None:
                            set_float(ori, "DiamDepth", matched.orifice_diameter)
                            set_float(ori, "CDO", matched.orifice_cdo)
                            set_float(ori, "IL", matched.il)
                            set_float(ori, "DesignDepth", matched.design_depth)
                            set_float(ori, "DesignFlow", matched.design_flow)
                    elif otype == OutletType.WEIR.value:
                        weir = odet_elem.find("CtrlWeir")
                        if weir is not None:
                            set_float(weir, "Width", matched.weir_width)
                            set_float(weir, "CDW", matched.weir_cdw)
                            set_float(weir, "IL", matched.il)
                    elif otype == OutletType.FLOW_CONTROL.value:
                        fc = odet_elem.find("FlowControl")
                        if fc is not None:
                            set_float(fc, "IL", matched.il)
                            set_float(fc, "DesignDepth", matched.design_depth)
                            set_float(fc, "DesignFlow", matched.design_flow)

            return elem

        elem = Element("jt")
        set_int(elem, "Index", idx)
        elem.set("Label", self.label)
        elem.set("IcoIndex", "33")
        set_bool(elem, "IsOut", self.is_outfall)
        set_int(elem, "OutType", 0)
        set_int(elem, "Type", self.junction_type.value)
        set_int(elem, "Shape", self.shape.value)
        set_float(elem, "Width", self.width)
        set_float(elem, "Length", self.length)
        set_float(elem, "Diameter", self.diameter)
        set_float(elem, "CL", self.cover_level)
        set_float(elem, "IL", self.invert_level)
        set_float(elem, "Depth", self.depth)
        set_float(elem, "SumpDepth", self.sump_depth)
        set_int(elem, "DepSet", 0)
        set_bool(elem, "IsAccessRequired", False)
        set_bool(elem, "Sealed", self.sealed)
        set_int(elem, "Lock", 0)
        set_int(elem, "PartFamily", self.part_family)
        set_float(elem, "BendLoss", self.bend_loss)
        elem.set("GUID", self.guid)

        elem.append(make_coordinate_2d(self.x, self.y))

        inlet_dets_elem = Element("InletDetails")
        for idet in self.inlets:
            ie = Element("IDetail")
            set_int(ie, "Index", idet.index)
            ie.set("Label", idet.label)
            ie.set("ftGUID", idet.parent_guid or self.guid)
            set_int(ie, "Type", 0)
            set_int(ie, "ICapType", 0)
            set_int(ie, "Dest", 0)
            ie.set("GUID", idet.guid)
            bc = Element("BCGUID")
            bc.set("ToLabel", "")
            ie.append(bc)
            guids_elem = Element("GUIDS")
            for si, src in enumerate(idet.sources):
                fs = Element("FromSource")
                set_int(fs, "Index", si)
                fs.set("ftGUID", src.guid)
                fs.set("FromLabel", src.label)
                guids_elem.append(fs)
            ie.append(guids_elem)
            hec = Element("HEC22InletResults")
            for a in ("Hec22ApproachFlow", "Hec22BypassFlow", "Hec22CapturedFlow",
                       "Hec22SpreadBypass", "Hec22SpreadGutter",
                       "Hec22DepthBypass", "Hec22DepthGutter"):
                set_float(hec, a, 0)
            ie.append(hec)
            inlet_dets_elem.append(ie)
        elem.append(inlet_dets_elem)

        outlet_dets_elem = Element("OutletDetails")
        for odet in self.outlets:
            outlet_dets_elem.append(odet.to_xml())
        elem.append(outlet_dets_elem)

        outfall = Element("OutFallDet")
        set_float(outfall, "FixLvl", 0)
        outfall.set("LvlCurveGUID", "")
        outfall.set("RainfallGuid", "")
        set_bool(outfall, "OutGated", False)
        outfall.append(Element("StrOutMaps"))
        elem.append(outfall)

        intersection = Element("Intersection")
        intersection.set("X", str(self.x))
        intersection.set("Y", str(self.y))
        elem.append(intersection)
        return elem


# ---------------------------------------------------------------------------
# DrainageSystem (Pond, Tank, Swale, etc.)
# ---------------------------------------------------------------------------

@dataclass
class DepthAreaVolume:
    """A single row in a depth-area-volume table."""
    depth: float = 0.0
    area: float = 0.0
    volume: float = 0.0


@dataclass
class DrainageSystem:
    """Represents a stormwater control (pond, tank, swale, bioretention, etc.)."""
    index: int = 0
    label: str = ""
    guid: str = field(default_factory=new_guid)
    system_type: DrainageSystemType = DrainageSystemType.POND
    x: float = 0.0
    y: float = 0.0
    is_outfall: bool = False
    cover_level: float = 0.0
    depth: float = 0.0
    invert_level: float = 0.0
    il_user: bool = False
    freeboard: float = 152.4
    top_area: float = 0.0
    base_area: float = 0.0
    side_slope: float = 0.0
    length: float = 0.0
    porosity: float = 100.0
    initial_depth: float = 0.0
    base_infiltration_on: bool = False
    base_infiltration_rate: float = 0.0
    side_infiltration_on: bool = False
    side_infiltration_rate: float = 0.0
    safety_factor_infil: float = 1.0
    mannings_n: float = 0.0
    # Swale-specific
    filtration_rate: float = 0.0
    swale_top_width: float = 0.0
    swale_base_width: float = 0.0
    trench_on: bool = False
    trench_porosity: float = 30.0
    conductivity: float = 0.0
    # Porous pavement-specific
    width: float = 0.0
    slope: float = 0.0
    membrane_permeability: float = 0.0
    # Chamber-specific
    inter_row_spacing: float = 0.0
    num_chambers: int = 0
    num_rows: int = 0
    chamber_type: int = 0
    # Bioretention-specific (sub-system references stored in raw XML)
    boundary: list[tuple[float, float]] = field(default_factory=list)
    centre_line: list[tuple[float, float]] = field(default_factory=list)
    depth_area_volume: list[DepthAreaVolume] = field(default_factory=list)
    inlets: list[InletDetail] = field(default_factory=list)
    outlets: list[OutletDetail] = field(default_factory=list)
    _raw_element: Optional[Element] = field(default=None, repr=False)
    _element_tag: str = "PondDSys"

    @classmethod
    def from_xml(cls, elem: Element) -> DrainageSystem:
        tag = elem.tag
        dsys_type = ELEMENT_TO_DSYS_TYPE.get(tag, DrainageSystemType.POND)

        coord = elem.find("Coordinate2D")
        x, y = parse_coordinate_2d(coord) if coord is not None else (0.0, 0.0)

        outline = elem.find("FreeFormOutlineDetails")
        boundary = []
        centre_line = []
        if outline is not None:
            boundary = parse_polygon(outline)
            cl_elem = outline.find("CentreLine")
            if cl_elem is not None:
                for c in cl_elem.findall("Coordinate2D"):
                    pt = parse_coordinate_2d(c)
                    if pt:
                        centre_line.append(pt)

        dav = []
        dav_elem = elem.find("DepAreVols")
        if dav_elem is not None:
            for row in dav_elem.findall("DepAreVol"):
                dav.append(DepthAreaVolume(
                    depth=get_float(row, "Depth"),
                    area=get_float(row, "SmallArea"),
                    volume=get_float(row, "PndStgVol"),
                ))

        inlets = []
        inlet_dets = elem.find("InletDetails")
        if inlet_dets is not None:
            for idet in inlet_dets.findall("IDetail"):
                sources = []
                guids_elem = idet.find("GUIDS")
                if guids_elem is not None:
                    for fs in guids_elem.findall("FromSource"):
                        sources.append(InletSource(
                            guid=get_str(fs, "ftGUID"),
                            label=get_str(fs, "FromLabel"),
                        ))
                inlets.append(InletDetail(
                    index=get_int(idet, "Index"),
                    label=get_str(idet, "Label", "Inlet"),
                    guid=get_str(idet, "GUID", new_guid()),
                    parent_guid=get_str(idet, "ftGUID"),
                    sources=sources,
                ))

        outlets = []
        outlet_dets = elem.find("OutletDetails")
        if outlet_dets is not None:
            for odet in outlet_dets.findall("ODetail"):
                outlets.append(OutletDetail.from_xml(odet))

        vel_dat = elem.find("VelCalcDat")
        mannings_n = 0.0
        if vel_dat is not None:
            mvc = vel_dat.find("ManningsVC")
            if mvc is not None:
                mannings_n = get_float(mvc, "ManningsN")

        return cls(
            index=get_int(elem, "Index"),
            label=get_str(elem, "Label"),
            guid=get_str(elem, "GUID", new_guid()),
            system_type=dsys_type,
            x=x, y=y,
            is_outfall=get_bool(elem, "IsOut"),
            cover_level=get_float(elem, "CL"),
            depth=get_float(elem, "Depth"),
            invert_level=get_float(elem, "IL"),
            il_user=get_bool(elem, "IL_User"),
            freeboard=get_float(elem, "Freeboard", 152.4),
            top_area=get_float(elem, "TopArea"),
            base_area=get_float(elem, "BaseArea"),
            side_slope=get_float(elem, "SideSlope"),
            length=get_float(elem, "Length"),
            porosity=get_float(elem, "Porosity", 100),
            initial_depth=get_float(elem, "IniDep"),
            base_infiltration_on=get_bool(elem, "BaseInfOn"),
            base_infiltration_rate=get_float(elem, "BaseInfRte"),
            side_infiltration_on=get_bool(elem, "SideInfOn"),
            side_infiltration_rate=get_float(elem, "SideInfRte"),
            safety_factor_infil=get_float(elem, "SafetyFactorInfil", 1),
            mannings_n=mannings_n,
            filtration_rate=get_float(elem, "FiltRate"),
            swale_top_width=get_float(elem, "SwalTopWid"),
            swale_base_width=get_float(elem, "BaseWid"),
            trench_on=get_bool(elem, "TrenchOn"),
            trench_porosity=get_float(elem, "TrenchPoro", 30),
            conductivity=get_float(elem, "Cond"),
            width=get_float(elem, "Width"),
            slope=get_float(elem, "Slope"),
            membrane_permeability=get_float(elem, "MemPerc"),
            inter_row_spacing=get_float(elem, "InterRowSpacing"),
            num_chambers=get_int(elem, "NumChambers"),
            num_rows=get_int(elem, "NumRows"),
            chamber_type=get_int(elem, "ChType"),
            boundary=boundary,
            centre_line=centre_line,
            depth_area_volume=dav,
            inlets=inlets,
            outlets=outlets,
            _raw_element=elem,
            _element_tag=tag,
        )

    def to_xml(self, index: Optional[int] = None) -> Element:
        import copy as _copy
        idx = index if index is not None else self.index

        if self._raw_element is not None:
            elem = _copy.deepcopy(self._raw_element)
            set_int(elem, "Index", idx)
            elem.set("Label", self.label)
            elem.set("GUID", self.guid)
            set_bool(elem, "IsOut", self.is_outfall)
            set_float(elem, "CL", self.cover_level)
            set_float(elem, "Depth", self.depth)
            set_float(elem, "IL", self.invert_level)
            set_float(elem, "BaseArea", self.base_area)
            set_float(elem, "TopArea", self.top_area)
            set_float(elem, "SideSlope", self.side_slope)
            set_float(elem, "Porosity", self.porosity)
            set_float(elem, "Length", self.length)
            set_bool(elem, "BaseInfOn", self.base_infiltration_on)
            set_float(elem, "BaseInfRte", self.base_infiltration_rate)
            set_bool(elem, "SideInfOn", self.side_infiltration_on)
            set_float(elem, "SideInfRte", self.side_infiltration_rate)
            set_float(elem, "SafetyFactorInfil", self.safety_factor_infil)
            set_float(elem, "IniDep", self.initial_depth)
            set_float(elem, "Freeboard", self.freeboard)

            outlet_dets = elem.find("OutletDetails")
            if outlet_dets is not None:
                for odet_elem in outlet_dets.findall("ODetail"):
                    odet_guid = get_str(odet_elem, "GUID")
                    matched = next(
                        (o for o in self.outlets if o.guid == odet_guid), None
                    )
                    if matched is None:
                        continue
                    otype = get_int(odet_elem, "Type", 0)
                    if otype == OutletType.ORIFICE.value:
                        ori = odet_elem.find("CtrlOrifice")
                        if ori is not None:
                            set_float(ori, "DiamDepth", matched.orifice_diameter)
                            set_float(ori, "CDO", matched.orifice_cdo)
                            set_float(ori, "IL", matched.il)
                            set_float(ori, "DesignDepth", matched.design_depth)
                            set_float(ori, "DesignFlow", matched.design_flow)
                    elif otype == OutletType.WEIR.value:
                        weir = odet_elem.find("CtrlWeir")
                        if weir is not None:
                            set_float(weir, "Width", matched.weir_width)
                            set_float(weir, "CDW", matched.weir_cdw)
                            set_float(weir, "IL", matched.il)
                    elif otype == OutletType.FLOW_CONTROL.value:
                        fc = odet_elem.find("FlowControl")
                        if fc is not None:
                            set_float(fc, "IL", matched.il)
                            set_float(fc, "DesignDepth", matched.design_depth)
                            set_float(fc, "DesignFlow", matched.design_flow)

            return elem

        tag = DRAINAGE_SYSTEM_ELEMENTS.get(self.system_type, "PondDSys")
        elem = Element(tag)
        set_int(elem, "Index", idx)
        elem.set("Label", self.label)
        elem.set("IcoIndex", "20")
        set_bool(elem, "IsOut", self.is_outfall)
        set_int(elem, "OutType", 0)
        set_bool(elem, "LockS", False)
        set_bool(elem, "ATWQv", True)
        set_int(elem, "OutlineType", 0)
        set_int(elem, "DepSet", 0)
        set_float(elem, "CL", self.cover_level)
        set_float(elem, "Depth", self.depth)
        set_float(elem, "IL", self.invert_level)
        if self.il_user:
            set_bool(elem, "IL_User", True)
        set_float(elem, "Freeboard", self.freeboard)
        set_bool(elem, "BaseInfOn", self.base_infiltration_on)
        set_float(elem, "BaseInfRte", self.base_infiltration_rate)
        set_bool(elem, "SideInfOn", self.side_infiltration_on)
        set_float(elem, "SideInfRte", self.side_infiltration_rate)
        set_float(elem, "SafetyFactorInfil", self.safety_factor_infil)
        set_float(elem, "InterVol", 0)
        set_float(elem, "EvapoTran", 0)
        set_float(elem, "Length", self.length)
        set_int(elem, "CrossSet", 0)
        set_float(elem, "TopArea", self.top_area)
        set_float(elem, "SideSlope", self.side_slope)
        set_float(elem, "BaseArea", self.base_area)
        set_float(elem, "IniDep", self.initial_depth)
        set_float(elem, "Porosity", self.porosity)
        set_float(elem, "AvSlope", 0)
        set_int(elem, "EditCol", 0)
        set_int(elem, "PerimType", 0)
        elem.set("GUID", self.guid)

        elem.append(make_coordinate_2d(self.x, self.y))

        inlet_dets_elem = Element("InletDetails")
        for idet in self.inlets:
            ie = Element("IDetail")
            set_int(ie, "Index", idet.index)
            ie.set("Label", idet.label)
            ie.set("ftGUID", idet.parent_guid or self.guid)
            set_int(ie, "Type", 0)
            set_int(ie, "ICapType", 0)
            set_int(ie, "Dest", 0)
            ie.set("GUID", idet.guid)
            bc = Element("BCGUID")
            bc.set("ToLabel", "")
            ie.append(bc)
            guids_elem = Element("GUIDS")
            for si, src in enumerate(idet.sources):
                fs = Element("FromSource")
                set_int(fs, "Index", si)
                fs.set("ftGUID", src.guid)
                fs.set("FromLabel", src.label)
                guids_elem.append(fs)
            ie.append(guids_elem)
            inlet_dets_elem.append(ie)
        elem.append(inlet_dets_elem)

        outlet_dets_elem = Element("OutletDetails")
        for odet in self.outlets:
            outlet_dets_elem.append(odet.to_xml())
        elem.append(outlet_dets_elem)

        outfall = Element("OutFallDet")
        set_float(outfall, "FixLvl", 0)
        outfall.set("LvlCurveGUID", "")
        outfall.set("RainfallGuid", "")
        set_bool(outfall, "OutGated", False)
        outfall.append(Element("StrOutMaps"))
        elem.append(outfall)

        size_calc = Element("SizeCalc")
        set_int(size_calc, "SizeMethod", 0)
        set_float(size_calc, "SideSlope", self.side_slope)
        set_float(size_calc, "Scale", 0)
        set_float(size_calc, "Volume", 0)
        set_int(size_calc, "UpPrmSelIdx", 0)
        set_int(size_calc, "DesignLevel", 0)
        elem.append(size_calc)

        if self.boundary or self.centre_line:
            outline = Element("FreeFormOutlineDetails")
            set_bool(outline, "CentreLineLocked", False)
            cl = Element("CentreLine")
            for i, (cx, cy) in enumerate(self.centre_line):
                cl.append(make_coordinate_2d(cx, cy, index=i))
            outline.append(cl)
            coord2ds = Element("Coord2Ds")
            for i, (bx, by) in enumerate(self.boundary):
                coord2ds.append(make_coordinate_2d(bx, by, index=i))
            outline.append(coord2ds)
            outline.append(Element("BaseCoords"))
            elem.append(outline)

        elem.append(Element("PollRems"))

        vel = Element("VelCalcDat")
        set_int(vel, "VelocityCalculationType", 0)
        mvc = Element("ManningsVC")
        set_float(mvc, "ManningsN", self.mannings_n)
        vel.append(mvc)
        elem.append(vel)

        if self.depth_area_volume:
            dav_elem = Element("DepAreVols")
            for i, row in enumerate(self.depth_area_volume):
                dav_row = Element("DepAreVol")
                set_int(dav_row, "Index", i)
                set_float(dav_row, "Depth", row.depth)
                set_float(dav_row, "SmallArea", row.area)
                set_float(dav_row, "PndStgVol", row.volume)
                dav_elem.append(dav_row)
            elem.append(dav_elem)

        return elem
