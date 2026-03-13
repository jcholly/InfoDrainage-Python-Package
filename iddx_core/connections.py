"""Connection classes: Pipes, culverts, and channels."""

from __future__ import annotations
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element
from typing import Optional

from .enums import ConnectionType, CONNECTION_ELEMENTS, ELEMENT_TO_CONNECTION_TYPE
from .utils import (
    get_float, get_int, get_bool, get_str, set_float, set_int, set_bool,
    new_guid,
)

TAG_FOR_TYPE = {
    ConnectionType.CIRCULAR_PIPE: "PipeCon",
    ConnectionType.TRAPEZOIDAL_CHANNEL: "TrapChan",
    ConnectionType.TRIANGULAR_CHANNEL: "TriChan",
}


@dataclass
class Connection:
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
    from_junction_guid: str = ""
    from_junction_label: str = ""
    to_junction_guid: str = ""
    to_junction_label: str = ""
    coords_3d: list[tuple[float, float, float]] = field(default_factory=list)
    _element_tag: str = "PipeCon"
    _raw_element: Optional[Element] = field(default=None, repr=False)

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
                coords_3d.append((
                    get_float(c, "X"),
                    get_float(c, "Y"),
                    get_float(c, "Z"),
                ))

        tag = elem.tag
        conn_type_int = get_int(elem, "Type", 2)
        if tag in ELEMENT_TO_CONNECTION_TYPE:
            conn_type = ELEMENT_TO_CONNECTION_TYPE[tag]
        else:
            try:
                conn_type = ConnectionType(conn_type_int)
            except ValueError:
                conn_type = ConnectionType.CIRCULAR_PIPE

        return cls(
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
            from_junction_guid=from_guid,
            from_junction_label=from_label,
            to_junction_guid=to_guid,
            to_junction_label=to_label,
            coords_3d=coords_3d,
            _element_tag=tag,
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
