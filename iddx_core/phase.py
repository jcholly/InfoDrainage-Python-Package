"""Phase class: container for all model elements in a single design phase."""

from __future__ import annotations
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element
from typing import Optional

from .enums import PhaseType, ALL_DSYS_TAGS, ALL_CONNECTION_TAGS
from .nodes import Catchment, Junction, DrainageSystem
from .connections import Connection
from .utils import (
    get_int, get_bool, get_str, get_float, set_int, set_bool, set_float,
    new_guid, find_or_create, make_ver_guid,
)


@dataclass
class Phase:
    """A design phase containing all network elements."""
    index: int = 0
    label: str = ""
    guid: str = field(default_factory=new_guid)
    phase_type: PhaseType = PhaseType.STORM
    analyse: bool = True
    visible: bool = True
    ver_guid: str = field(default_factory=make_ver_guid)
    catchments: list[Catchment] = field(default_factory=list)
    junctions: list[Junction] = field(default_factory=list)
    drainage_systems: list[DrainageSystem] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    _raw_element: Optional[Element] = field(default=None, repr=False)

    # -- Lookups -----------------------------------------------------------

    def find_catchment(self, label: str) -> Optional[Catchment]:
        for c in self.catchments:
            if c.label == label:
                return c
        return None

    def find_junction(self, label: str) -> Optional[Junction]:
        for j in self.junctions:
            if j.label == label:
                return j
        return None

    def find_junction_by_guid(self, guid: str) -> Optional[Junction]:
        for j in self.junctions:
            if j.guid == guid:
                return j
        return None

    def find_drainage_system(self, label: str) -> Optional[DrainageSystem]:
        for ds in self.drainage_systems:
            if ds.label == label:
                return ds
        return None

    def find_connection(self, label: str) -> Optional[Connection]:
        for c in self.connections:
            if c.label == label:
                return c
        return None

    # -- Mutators ----------------------------------------------------------

    def add_catchment(self, catchment: Catchment) -> Catchment:
        catchment.index = len(self.catchments)
        self.catchments.append(catchment)
        return catchment

    def add_junction(self, junction: Junction) -> Junction:
        junction.index = len(self.junctions)
        self.junctions.append(junction)
        return junction

    def add_drainage_system(self, ds: DrainageSystem) -> DrainageSystem:
        ds.index = len(self.drainage_systems)
        self.drainage_systems.append(ds)
        return ds

    def add_connection(self, conn: Connection) -> Connection:
        conn.index = len(self.connections)
        self.connections.append(conn)
        return conn

    def remove_catchment(self, label: str) -> bool:
        c = self.find_catchment(label)
        if c:
            self.catchments.remove(c)
            self._reindex_catchments()
            return True
        return False

    def remove_junction(self, label: str) -> bool:
        j = self.find_junction(label)
        if j:
            self.junctions.remove(j)
            self._reindex_junctions()
            return True
        return False

    def remove_connection(self, label: str) -> bool:
        c = self.find_connection(label)
        if c:
            self.connections.remove(c)
            self._reindex_connections()
            return True
        return False

    def _reindex_catchments(self) -> None:
        for i, c in enumerate(self.catchments):
            c.index = i

    def _reindex_junctions(self) -> None:
        for i, j in enumerate(self.junctions):
            j.index = i

    def _reindex_connections(self) -> None:
        for i, c in enumerate(self.connections):
            c.index = i

    # -- Summary -----------------------------------------------------------

    @property
    def total_catchment_area(self) -> float:
        return sum(c.area for c in self.catchments)

    @property
    def total_pipe_length(self) -> float:
        return sum(c.length for c in self.connections)

    @property
    def num_outfalls(self) -> int:
        count = sum(1 for j in self.junctions if j.is_outfall)
        count += sum(1 for ds in self.drainage_systems if ds.is_outfall)
        return count

    def summary(self) -> dict:
        return {
            "label": self.label,
            "catchments": len(self.catchments),
            "junctions": len(self.junctions),
            "drainage_systems": len(self.drainage_systems),
            "connections": len(self.connections),
            "outfalls": self.num_outfalls,
            "total_catchment_area_sqmi": round(self.total_catchment_area, 6),
            "total_pipe_length": round(self.total_pipe_length, 2),
        }

    # -- Parsing -----------------------------------------------------------

    @classmethod
    def from_xml(cls, elem: Element) -> Phase:
        catchments = []
        junctions = []
        drainage_systems = []
        connections = []

        nodes = elem.find("Nodes")
        if nodes is not None:
            inflow = nodes.find("InflowNodes")
            if inflow is not None:
                for ain in inflow.findall("AreaInflowNode"):
                    catchments.append(Catchment.from_xml(ain))

            dsys_container = nodes.find("DrainageSystems")
            if dsys_container is not None:
                for tag in ALL_DSYS_TAGS:
                    for ds_elem in dsys_container.findall(tag):
                        drainage_systems.append(DrainageSystem.from_xml(ds_elem))

            juncs = nodes.find("Junctions")
            if juncs is not None:
                for jt in juncs.findall("jt"):
                    junctions.append(Junction.from_xml(jt))

        conexs = elem.find("Conexs")
        if conexs is not None:
            for tag in ALL_CONNECTION_TAGS:
                for conn_elem in conexs.findall(tag):
                    connections.append(Connection.from_xml(conn_elem))

        return cls(
            index=get_int(elem, "Index"),
            label=get_str(elem, "Label"),
            guid=get_str(elem, "GUID", new_guid()),
            phase_type=PhaseType(get_int(elem, "PhaseType", 0)),
            analyse=get_bool(elem, "Analyse", True),
            visible=get_bool(elem, "Vis", True),
            ver_guid=get_str(elem, "verGuid", make_ver_guid()),
            catchments=catchments,
            junctions=junctions,
            drainage_systems=drainage_systems,
            connections=connections,
            _raw_element=elem,
        )

    def to_xml(self, index: Optional[int] = None) -> Element:
        import copy as _copy
        idx = index if index is not None else self.index

        if self._raw_element is not None:
            elem = _copy.deepcopy(self._raw_element)
            set_int(elem, "Index", idx)
            elem.set("GUID", self.guid)
            elem.set("Label", self.label)
            set_bool(elem, "Analyse", self.analyse)
            set_int(elem, "PhaseType", self.phase_type.value)
            set_bool(elem, "Vis", self.visible)
            elem.set("verGuid", self.ver_guid)

            nodes = elem.find("Nodes")
            if nodes is not None:
                old_inflow = nodes.find("InflowNodes")
                if old_inflow is not None:
                    nodes.remove(old_inflow)
                inflow_nodes = Element("InflowNodes")
                for i, c in enumerate(self.catchments):
                    inflow_nodes.append(c.to_xml(index=i))
                nodes.insert(0, inflow_nodes)

                old_dsys = nodes.find("DrainageSystems")
                if old_dsys is not None:
                    nodes.remove(old_dsys)
                dsys_elem = Element("DrainageSystems")
                for i, ds in enumerate(self.drainage_systems):
                    dsys_elem.append(ds.to_xml(index=i))
                nodes.insert(1, dsys_elem)

                old_juncs = nodes.find("Junctions")
                if old_juncs is not None:
                    nodes.remove(old_juncs)
                juncs_elem = Element("Junctions")
                for i, j in enumerate(self.junctions):
                    juncs_elem.append(j.to_xml(index=i))
                nodes.insert(2, juncs_elem)

            old_conexs = elem.find("Conexs")
            if old_conexs is not None:
                elem.remove(old_conexs)
            conexs = Element("Conexs")
            for i, c in enumerate(self.connections):
                conexs.append(c.to_xml(index=i))
            if nodes is not None:
                nodes_idx = list(elem).index(nodes)
                elem.insert(nodes_idx + 1, conexs)
            else:
                elem.append(conexs)

            return elem

        elem = Element("Phase")
        set_int(elem, "Index", idx)
        elem.set("GUID", self.guid)
        elem.set("Label", self.label)
        set_bool(elem, "Analyse", self.analyse)
        set_int(elem, "PhaseType", self.phase_type.value)
        set_bool(elem, "Vis", self.visible)
        elem.set("verGuid", self.ver_guid)

        nodes = Element("Nodes")

        inflow_nodes = Element("InflowNodes")
        for i, c in enumerate(self.catchments):
            inflow_nodes.append(c.to_xml(index=i))
        nodes.append(inflow_nodes)

        dsys_elem = Element("DrainageSystems")
        for i, ds in enumerate(self.drainage_systems):
            dsys_elem.append(ds.to_xml(index=i))
        nodes.append(dsys_elem)

        juncs_elem = Element("Junctions")
        for i, j in enumerate(self.junctions):
            juncs_elem.append(j.to_xml(index=i))
        nodes.append(juncs_elem)

        nodes.append(Element("LandUseObjCol"))
        nodes.append(Element("SoilTypeObjCol"))
        elem.append(nodes)

        conexs = Element("Conexs")
        for i, c in enumerate(self.connections):
            conexs.append(c.to_xml(index=i))
        elem.append(conexs)

        for tag in ("Paths", "SurfFile", "CADFiles", "GISFiles",
                     "BackImages", "WatrQual", "AnaResFiles",
                     "AnalysisRuns", "LevelHyds", "PartsMappings", "LUCache"):
            elem.append(Element(tag))

        qse = Element("QSE")
        qse.append(Element("RainGuidPairs"))
        qse_res = Element("QSERes")
        for a in ("MinNoIn", "MaxNoIn", "MinIn", "MaxIn"):
            set_int(qse_res, a, 0)
        qse.append(qse_res)
        elem.append(qse)

        ff_calc = Element("FirstFlushCalc")
        ff_calc.append(Element("RainGuidPairs"))
        elem.append(ff_calc)

        method_des = Element("MethodDesPluiesCalc")
        method_des.append(Element("RainGuidPairs"))
        elem.append(method_des)

        ff_data_phase = Element("FFData")
        set_int(ff_data_phase, "ElemArea", 9290304)
        set_float(ff_data_phase, "ManningsN", 0.03)
        set_float(ff_data_phase, "StartDepth", 0)
        set_float(ff_data_phase, "Scale", 1)
        ff_data_phase.append(Element("RainGuidPairs"))
        elem.append(ff_data_phase)

        elem.append(Element("StormNetDesCrit"))

        return elem

    def clone(self, new_label: str) -> Phase:
        """Create a deep copy of this phase with a new label and new GUIDs.

        Uses raw XML deep copy when available to preserve all elements
        (AnalysisRuns, connectivity details, etc.) that the Python model
        doesn't explicitly manage.
        """
        import copy as _copy

        if self._raw_element is not None:
            new_elem = _copy.deepcopy(self._raw_element)
            new_elem.set("Label", new_label)
            new_elem.set("GUID", new_guid())
            new_elem.set("verGuid", make_ver_guid())
            return Phase.from_xml(new_elem)

        xml = self.to_xml()
        new_phase = Phase.from_xml(xml)
        new_phase.label = new_label
        new_phase.guid = new_guid()
        new_phase.ver_guid = make_ver_guid()
        return new_phase
