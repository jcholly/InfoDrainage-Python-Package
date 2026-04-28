"""Connection classes: Pipes, culverts, channels, and bypass connections."""

from __future__ import annotations
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element
from typing import Optional

from .enums import ConnectionType, ELEMENT_TO_CONNECTION_TYPE
from .utils import (
    RawXmlBacked,
    get_float,
    get_int,
    get_bool,
    get_str,
    set_float,
    set_int,
    set_bool,
    new_guid,
)

TAG_FOR_TYPE = {
    ConnectionType.CIRCULAR_PIPE: "PipeCon",
    ConnectionType.TRAPEZOIDAL_CHANNEL: "TrapChan",
    ConnectionType.TRIANGULAR_CHANNEL: "TriChan",
    ConnectionType.CUSTOM_BYPASS: "CustomCon",
}


@dataclass
class CrossSectionPoint:
    """A single point in a custom cross-section profile."""

    x: float = 0.0
    y: float = 0.0


@dataclass
class CrossSectionDetails:
    """Custom cross-section geometry for CustomCon bypass connections."""

    con_covered: bool = False
    diameter: float = 0.0
    points: list[CrossSectionPoint] = field(default_factory=list)

    @classmethod
    def from_xml(cls, elem: Element) -> CrossSectionDetails:
        pts = []
        coords = elem.find("Coords2DShort")
        if coords is not None:
            for c in coords.findall("Coordinate2DShort"):
                pts.append(
                    CrossSectionPoint(
                        x=get_float(c, "XSh"),
                        y=get_float(c, "YSh"),
                    )
                )
        return cls(
            con_covered=get_bool(elem, "ConCovered"),
            diameter=get_float(elem, "Diam"),
            points=pts,
        )

    def to_xml(self) -> Element:
        elem = Element("CrsSctDetails")
        set_bool(elem, "ConCovered", self.con_covered)
        set_float(elem, "Diam", self.diameter)
        coords = Element("Coords2DShort")
        for i, pt in enumerate(self.points):
            c = Element("Coordinate2DShort")
            set_int(c, "Index", i)
            set_float(c, "XSh", pt.x)
            set_float(c, "YSh", pt.y)
            coords.append(c)
        elem.append(coords)
        return elem


@dataclass
class RationalResults:
    """Rational-method design results stored on a connection (read-only output)."""

    path_guid: str = ""
    rainfall_intensity: float = 0.0
    time_of_concentration: float = 0.0
    proportional_velocity: float = 0.0
    proportional_depth: float = 0.0
    velocity: float = 0.0
    capacity: float = 0.0
    flow: float = 0.0
    cv: float = 0.0
    cs: float = 0.0
    capacity_limit: float = 0.0
    velocity_at_one_third: float = 0.0

    @classmethod
    def from_xml(cls, elem: Element) -> RationalResults:
        return cls(
            path_guid=get_str(elem, "PathGUID"),
            rainfall_intensity=get_float(elem, "RainfallIntensity"),
            time_of_concentration=get_float(elem, "ToT"),
            proportional_velocity=get_float(elem, "ProVel"),
            proportional_depth=get_float(elem, "ProDep"),
            velocity=get_float(elem, "Vel"),
            capacity=get_float(elem, "Cap"),
            flow=get_float(elem, "Flow"),
            cv=get_float(elem, "Cv"),
            cs=get_float(elem, "CS"),
            capacity_limit=get_float(elem, "CapLimPipeCon"),
            velocity_at_one_third=get_float(elem, "ProVelAtOneThirdFlow"),
        )


@dataclass
class UpstreamTotals:
    """Upstream accumulation totals stored on a connection (read-only output)."""

    base_flow: float = 0.0
    area: float = 0.0
    contributing_area: float = 0.0
    impervious_area: float = 0.0
    total_discharge_units: float = 0.0
    total_dwellings: float = 0.0
    foul_flow_rate: float = 0.0
    total_unit_flow: float = 0.0

    @classmethod
    def from_xml(cls, elem: Element) -> UpstreamTotals:
        return cls(
            base_flow=get_float(elem, "BaseFlow"),
            area=get_float(elem, "Area"),
            contributing_area=get_float(elem, "ContArea"),
            impervious_area=get_float(elem, "PimpArea"),
            total_discharge_units=get_float(elem, "TotalDisUnits"),
            total_dwellings=get_float(elem, "TotalDwellings"),
            foul_flow_rate=get_float(elem, "FoulResultingFlowRate"),
            total_unit_flow=get_float(elem, "TotalUnitFlow"),
        )


@dataclass(kw_only=True)
class Connection(RawXmlBacked):
    """Represents a pipe, channel, or culvert connection between two nodes."""

    index: int = 0
    label: str = ""
    guid: str = field(default_factory=new_guid)
    connection_type: ConnectionType = ConnectionType.CIRCULAR_PIPE
    length: float = 0.0
    design_flow: float = 0.0
    us_cover_level: float = 0.0
    us_invert_level: float = 0.0
    ds_cover_level: float = 0.0
    ds_invert_level: float = 0.0
    slope: float = 0.0
    diameter: float = 381.0
    conduit_height: float = 0.0
    side_slope: float = 0.0
    num_barrels: int = 1
    entry_loss: float = 0.5
    exit_loss: float = 0.0
    avg_loss: float = 0.0
    mannings_n: float = 0.013
    curved: bool = False
    part_family: int = 0
    part_wall_thickness: float = 0.0
    part_material: str = ""
    conduit_height_user: bool = False
    from_junction_guid: str = ""
    from_junction_label: str = ""
    to_junction_guid: str = ""
    to_junction_label: str = ""
    coords_3d: list[tuple[float, float, float]] = field(default_factory=list)
    cross_section: Optional[CrossSectionDetails] = None
    rational_results: Optional[RationalResults] = None
    upstream_totals: Optional[UpstreamTotals] = None
    _element_tag: str = field(default="PipeCon", init=False, repr=False, compare=False)
    _raw_element: Optional[Element] = field(
        default=None, init=False, repr=False, compare=False
    )

    @property
    def diameter_inches(self) -> float:
        return self.diameter / 25.4

    @property
    def diameter_meters(self) -> float:
        return self.diameter / 1000.0

    @property
    def is_channel(self) -> bool:
        return self.connection_type in (
            ConnectionType.TRAPEZOIDAL_CHANNEL,
            ConnectionType.TRIANGULAR_CHANNEL,
        )

    @property
    def is_bypass(self) -> bool:
        return self.connection_type == ConnectionType.CUSTOM_BYPASS

    @property
    def calculated_slope(self) -> float:
        """Calculate slope as rise/run (1:X)."""
        if self.length <= 0:
            return 0.0
        rise = self.us_invert_level - self.ds_invert_level
        if rise == 0:
            return 0.0
        return self.length / rise

    @classmethod
    def from_xml(cls, elem: Element) -> Connection:
        from_src = elem.find("FromSource")
        from_guid = get_str(from_src, "ftGUID") if from_src is not None else ""
        from_label = get_str(from_src, "FromLabel") if from_src is not None else ""

        to_dest = elem.find("ToDest")
        to_guid = get_str(to_dest, "ftGUID") if to_dest is not None else ""
        to_label = get_str(to_dest, "ToLabel") if to_dest is not None else ""

        mannings_n = 0.013
        mvc = elem.find("ManningsVC")
        if mvc is not None:
            mannings_n = get_float(mvc, "ManningsN", 0.013)

        coords_3d = []
        c3d_elem = elem.find("Coord3Ds")
        if c3d_elem is not None:
            for c in c3d_elem.findall("Coordinate3D"):
                coords_3d.append(
                    (
                        get_float(c, "X"),
                        get_float(c, "Y"),
                        get_float(c, "Z"),
                    )
                )

        cross_section = None
        crs_elem = elem.find("CrsSctDetails")
        if crs_elem is not None:
            cross_section = CrossSectionDetails.from_xml(crs_elem)

        rat_res = None
        rat_elem = elem.find("RatRes")
        if rat_elem is not None:
            rat_res = RationalResults.from_xml(rat_elem)

        us_tot = None
        us_elem = elem.find("USTot")
        if us_elem is not None:
            us_tot = UpstreamTotals.from_xml(us_elem)

        tag = elem.tag
        conn_type_int = get_int(elem, "Type", 2)
        if tag in ELEMENT_TO_CONNECTION_TYPE:
            conn_type = ELEMENT_TO_CONNECTION_TYPE[tag]
        else:
            try:
                conn_type = ConnectionType(conn_type_int)
            except ValueError:
                conn_type = ConnectionType.CIRCULAR_PIPE

        obj = cls(
            index=get_int(elem, "Index"),
            label=get_str(elem, "Label"),
            guid=get_str(elem, "GUID", new_guid()),
            connection_type=conn_type,
            length=get_float(elem, "Length"),
            design_flow=get_float(elem, "DesignFlow"),
            us_cover_level=get_float(elem, "USCL"),
            us_invert_level=get_float(elem, "USIL"),
            ds_cover_level=get_float(elem, "DSCL"),
            ds_invert_level=get_float(elem, "DSIL"),
            slope=get_float(elem, "Slope"),
            diameter=get_float(elem, "Diam", 381),
            conduit_height=get_float(elem, "ConduitHeight"),
            side_slope=get_float(elem, "SideSlope"),
            num_barrels=get_int(elem, "NoBarrels", 1),
            entry_loss=get_float(elem, "EntryLoss", 0.5),
            exit_loss=get_float(elem, "ExitLoss"),
            avg_loss=get_float(elem, "AvgLoss"),
            mannings_n=mannings_n,
            curved=get_bool(elem, "Curved"),
            part_family=get_int(elem, "PartFamily"),
            part_wall_thickness=get_float(elem, "PartWallThickness"),
            part_material=get_str(elem, "PartMaterial"),
            conduit_height_user=get_bool(elem, "ConduitHeight_User"),
            from_junction_guid=from_guid,
            from_junction_label=from_label,
            to_junction_guid=to_guid,
            to_junction_label=to_label,
            coords_3d=coords_3d,
            cross_section=cross_section,
            rational_results=rat_res,
            upstream_totals=us_tot,
        )
        obj._element_tag = tag
        obj._raw_element = elem
        return obj

    def to_xml(self, index: Optional[int] = None) -> Element:
        idx = index if index is not None else self.index

        elem = self._copy_raw()
        if elem is not None:
            set_int(elem, "Index", idx)
            elem.set("Label", self.label)
            elem.set("GUID", self.guid)
            set_float(elem, "Diam", self.diameter)
            set_float(elem, "Length", self.length)
            set_float(elem, "USIL", self.us_invert_level)
            set_float(elem, "DSIL", self.ds_invert_level)
            set_float(elem, "USCL", self.us_cover_level)
            set_float(elem, "DSCL", self.ds_cover_level)
            set_float(elem, "Slope", self.slope)
            set_float(elem, "EntryLoss", self.entry_loss)
            set_float(elem, "ExitLoss", self.exit_loss)
            set_float(elem, "AvgLoss", self.avg_loss)
            set_int(elem, "NoBarrels", self.num_barrels)
            set_bool(elem, "Curved", self.curved)
            set_float(elem, "ConduitHeight", self.conduit_height)
            set_float(elem, "SideSlope", self.side_slope)
            set_int(elem, "PartFamily", self.part_family)

            from_src = elem.find("FromSource")
            if from_src is not None:
                from_src.set("ftGUID", self.from_junction_guid)
                from_src.set("FromLabel", self.from_junction_label)

            to_dest = elem.find("ToDest")
            if to_dest is not None:
                to_dest.set("ftGUID", self.to_junction_guid)
                to_dest.set("ToLabel", self.to_junction_label)

            mvc = elem.find("ManningsVC")
            if mvc is not None:
                set_float(mvc, "ManningsN", self.mannings_n)
            return elem

        tag = TAG_FOR_TYPE.get(self.connection_type, "PipeCon")
        elem = Element(tag)
        set_int(elem, "Index", idx)
        elem.set("Label", self.label)
        set_int(elem, "Type", self.connection_type.value)
        set_float(elem, "Length", self.length)
        set_float(elem, "DesignFlow", self.design_flow)
        set_float(elem, "USCL", self.us_cover_level)
        set_float(elem, "USIL", self.us_invert_level)
        set_float(elem, "DSCL", self.ds_cover_level)
        set_float(elem, "DSIL", self.ds_invert_level)
        set_bool(elem, "Curved", self.curved)
        set_float(elem, "Slope", self.slope)
        set_float(elem, "MinCDPer", 0)
        set_float(elem, "MinDSIL", 0)
        set_int(elem, "Lock", 0)
        set_int(elem, "VelocityCalculationType", 0)
        set_int(elem, "NoBarrels", self.num_barrels)
        set_float(elem, "EntryLoss", self.entry_loss)
        set_float(elem, "ExitLoss", self.exit_loss)
        set_float(elem, "AvgLoss", self.avg_loss)
        set_int(elem, "PartFamily", self.part_family)

        if self.is_channel:
            set_float(elem, "SideSlope", self.side_slope)
            set_float(elem, "Diam", self.diameter)
            set_float(elem, "ConduitHeight", self.conduit_height)
        else:
            set_float(elem, "PartWallThickness", self.part_wall_thickness)
            elem.set("PartMaterial", self.part_material)
            elem.set("PartTrenchWidth", "0")
            elem.set("PartBeddingMaterial", "")
            elem.set("PartSurroundingMaterial", "")
            set_float(elem, "Diam", self.diameter)
            set_int(elem, "CulvertType", 0)
            set_int(elem, "CulvertEntrance", 0)

        elem.set("GUID", self.guid)

        from_src = Element("FromSource")
        from_src.set("ftGUID", self.from_junction_guid)
        from_src.set("FromLabel", self.from_junction_label)
        elem.append(from_src)

        to_dest = Element("ToDest")
        to_dest.set("ftGUID", self.to_junction_guid)
        to_dest.set("ToLabel", self.to_junction_label)
        elem.append(to_dest)

        elem.append(Element("Coord2Ds"))

        cur = Element("CurCoord")
        cur.set("X", "0")
        cur.set("Y", "0")
        elem.append(cur)

        elem.append(Element("CurveCoord2Ds"))

        mvc = Element("ManningsVC")
        set_float(mvc, "ManningsN", self.mannings_n)
        elem.append(mvc)

        if self.coords_3d:
            c3d_elem = Element("Coord3Ds")
            for i, (x, y, z) in enumerate(self.coords_3d):
                c = Element("Coordinate3D")
                set_int(c, "Index", i)
                c.set("X", str(x))
                c.set("Y", str(y))
                c.set("Z", str(z))
                c3d_elem.append(c)
            elem.append(c3d_elem)

        return elem


PipeConnection = Connection
