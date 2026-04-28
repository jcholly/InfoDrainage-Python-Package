"""Rainfall data classes: NOAA sources, storm events, and hyetographs."""

from __future__ import annotations
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element
from typing import Optional

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


@dataclass
class HyetographItem:
    """A single time-depth point in a storm hyetograph."""

    time: float = 0.0
    depth: float = 0.0

    @classmethod
    def from_xml(cls, elem: Element) -> HyetographItem:
        return cls(
            time=get_float(elem, "T"),
            depth=get_float(elem, "D"),
        )

    def to_xml(self, index: int) -> Element:
        elem = Element("Item")
        set_int(elem, "Index", index)
        if self.time > 0:
            set_float(elem, "T", self.time)
        set_float(elem, "D", self.depth)
        return elem


@dataclass
class StormEvent:
    """A single storm definition (duration + return period + hyetograph)."""

    index: int = 0
    duration_minutes: float = 1440.0
    return_period: float = 1.0
    use: bool = True
    ir_type: int = 6
    profile_type: int = 0
    guid: str = field(default_factory=new_guid)
    rainfall_guid: str = ""
    label: str = ""
    run_time: float = 1440.0
    hyetograph: list[HyetographItem] = field(default_factory=list)

    @property
    def total_depth(self) -> float:
        if not self.hyetograph:
            return 0.0
        return max(item.depth for item in self.hyetograph)

    @classmethod
    def from_xml(cls, strdet: Element) -> StormEvent:
        rpp = strdet.find("RetPerPair")
        strm = strdet.find("Strm")

        hyetograph = []
        if strm is not None:
            for item in strm.findall("Item"):
                hyetograph.append(HyetographItem.from_xml(item))

        return cls(
            index=get_int(strdet, "Index"),
            duration_minutes=get_float(strdet, "STag", 1440),
            return_period=get_float(rpp, "RetPer", 1) if rpp is not None else 1.0,
            use=get_bool(rpp, "Use", True) if rpp is not None else True,
            ir_type=get_int(rpp, "IRType", 6) if rpp is not None else 6,
            profile_type=get_int(strdet, "profType"),
            guid=get_str(rpp, "GUID", new_guid()) if rpp is not None else new_guid(),
            rainfall_guid=get_str(strdet, "RainfallGuid"),
            label=get_str(strm, "Label") if strm is not None else "",
            run_time=get_float(strm, "RunT", 1440) if strm is not None else 1440.0,
            hyetograph=hyetograph,
        )

    def to_xml_strdet(self, with_hyetograph: bool = False) -> Element:
        """Create a StrDet element (used in both StrmDetails and StrmViewerDetails)."""
        elem = Element("StrDet")
        set_int(elem, "Index", self.index)
        elem.set("STag", str(int(self.duration_minutes)))
        set_int(elem, "profType", self.profile_type)
        elem.set("RainfallGuid", self.rainfall_guid)
        set_bool(elem, "FirstFlushReqd", False)
        set_int(elem, "TPTag", 0)
        set_int(elem, "QuartileTag", 0)
        set_int(elem, "PercOfOccTag", 0)

        rpp = Element("RetPerPair")
        set_float(rpp, "RetPer", self.return_period)
        set_bool(rpp, "Use", self.use)
        set_int(rpp, "IRType", self.ir_type)
        rpp.set("GUID", self.guid)
        elem.append(rpp)

        strm = Element("Strm")
        if with_hyetograph and self.hyetograph:
            strm.set(
                "Label",
                self.label or f"{self.return_period:.3f}_{self.duration_minutes:.2f}",
            )
            strm.set("Time", "0001-01-01T00:00:00")
            set_float(strm, "RunT", self.run_time)
            for i, h in enumerate(self.hyetograph):
                strm.append(h.to_xml(i))
        else:
            strm.set("Time", "0001-01-01T00:00:00")
        elem.append(strm)
        return elem


@dataclass(kw_only=True)
class RainfallSource(RawXmlBacked):
    """A rainfall data source (NOAA, FEH, FSR, Custom)."""

    index: int = 0
    source_type: str = "NOAA"
    method: int = 1
    longitude: float = 0.0
    latitude: float = 0.0
    label: str = "NOAA"
    guid: str = field(default_factory=new_guid)
    ver_guid: str = field(default_factory=new_guid)
    storm_definitions: list[StormEvent] = field(default_factory=list)
    storm_hyetographs: list[StormEvent] = field(default_factory=list)
    _raw_element: Optional[Element] = field(
        default=None, init=False, repr=False, compare=False
    )

    @property
    def return_periods(self) -> list[float]:
        return [s.return_period for s in self.storm_definitions]

    @property
    def durations(self) -> list[float]:
        seen = []
        for s in self.storm_definitions:
            if s.duration_minutes not in seen:
                seen.append(s.duration_minutes)
        return seen

    def get_storm(
        self, return_period: float, duration: Optional[float] = None
    ) -> Optional[StormEvent]:
        """Find a storm event by return period and optionally duration."""
        for s in self.storm_hyetographs:
            if s.return_period == return_period:
                if duration is None or s.duration_minutes == duration:
                    return s
        return None

    @classmethod
    def from_xml(cls, elem: Element) -> RainfallSource:
        source_type = elem.tag
        storm_defs = []
        strm_details = elem.find("StrmDetails")
        if strm_details is not None:
            for sd in strm_details.findall("StrDet"):
                storm_defs.append(StormEvent.from_xml(sd))

        storm_hyetographs = []
        viewer_details = elem.find("StrmViewerDetails")
        if viewer_details is not None:
            for sd in viewer_details.findall("StrDet"):
                storm_hyetographs.append(StormEvent.from_xml(sd))

        obj = cls(
            index=get_int(elem, "Index"),
            source_type=source_type,
            method=get_int(elem, "Method", 1),
            longitude=get_float(elem, "Long"),
            latitude=get_float(elem, "Lat"),
            label=get_str(elem, "Lab", source_type),
            guid=get_str(elem, "Guid", new_guid()),
            ver_guid=get_str(elem, "verGuid", new_guid()),
            storm_definitions=storm_defs,
            storm_hyetographs=storm_hyetographs,
        )
        obj._raw_element = elem
        return obj

    def to_xml(self) -> Element:
        elem = self._copy_raw()
        if elem is not None:
            set_int(elem, "Index", self.index)
            elem.set("Lab", self.label)
            elem.set("Guid", self.guid)
            elem.set("verGuid", self.ver_guid)
            set_float(elem, "Long", self.longitude)
            set_float(elem, "Lat", self.latitude)
            return elem

        elem = Element(self.source_type)
        set_int(elem, "Index", self.index)
        set_int(elem, "Method", self.method)
        set_float(elem, "Long", self.longitude)
        set_float(elem, "Lat", self.latitude)
        elem.set("Lab", self.label)
        elem.set("Guid", self.guid)
        elem.set("verGuid", self.ver_guid)

        strm_details = Element("StrmDetails")
        for sd in self.storm_definitions:
            strm_details.append(sd.to_xml_strdet(with_hyetograph=False))
        elem.append(strm_details)

        viewer_details = Element("StrmViewerDetails")
        for sh in self.storm_hyetographs:
            viewer_details.append(sh.to_xml_strdet(with_hyetograph=True))
        elem.append(viewer_details)

        return elem
