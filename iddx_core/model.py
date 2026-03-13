"""IddxModel: top-level reader/writer for InfoDrainage .iddx project files."""

from __future__ import annotations
import copy
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .enums import ELEMENT_TO_DSYS_TYPE
from .phase import Phase
from .rainfall import RainfallSource
from .nodes import Catchment, Junction, DrainageSystem
from .connections import PipeConnection
from .utils import (
    get_int, get_bool, get_str, get_float, set_int, set_bool, set_float,
    new_guid, make_ver_guid, find_or_create,
)


RAINFALL_SOURCE_TAGS = ("NOAA", "FEH", "FSR", "CustomRain")


@dataclass
class AuthorInfo:
    product: str = "InfoDrainage"
    manufacturer: str = "Autodesk, Inc."
    version: str = ""
    user: str = ""
    date: str = ""


@dataclass
class UnitSettings:
    region: str = "United States"
    depth: int = 5
    short_length: int = 2
    medium_length: int = 5
    finish_length: int = 2
    small_area: int = 5
    large_area: int = 5
    volume: int = 4
    small_flow: int = 1
    medium_flow: int = 7
    large_flow: int = 2
    velocity: int = 2
    slope: int = 3
    rain: int = 1
    rain_depth: int = 1
    infiltration: int = 2


@dataclass
class IddxModel:
    """Top-level model object representing an InfoDrainage .iddx project file."""
    filepath: Optional[Path] = None
    author: AuthorInfo = field(default_factory=AuthorInfo)
    units: UnitSettings = field(default_factory=UnitSettings)
    db_ver_guid: str = ""
    phases: dict[str, Phase] = field(default_factory=dict)
    rainfall_sources: list[RainfallSource] = field(default_factory=list)
    _tree: Optional[ET.ElementTree] = field(default=None, repr=False)
    _root: Optional[Element] = field(default=None, repr=False)

    # -- Factory methods ---------------------------------------------------

    @classmethod
    def open(cls, filepath: str | Path) -> IddxModel:
        """Open and parse an existing .iddx file."""
        filepath = Path(filepath)
        tree = ET.parse(filepath)
        root = tree.getroot()

        author_elem = root.find("Author")
        author = AuthorInfo()
        if author_elem is not None:
            author = AuthorInfo(
                product=get_str(author_elem, "Product", "InfoDrainage"),
                manufacturer=get_str(author_elem, "Manufacturer", "Autodesk, Inc."),
                version=get_str(author_elem, "Version"),
                user=get_str(author_elem, "User"),
                date=get_str(author_elem, "Date"),
            )

        site = root.find("Site")
        db_ver_guid = get_str(site, "DBVerGUID") if site is not None else ""

        units = UnitSettings()
        if site is not None:
            u = site.find("Units")
            if u is not None:
                units = UnitSettings(
                    region=get_str(u, "Region", "United States"),
                    depth=get_int(u, "Depth", 5),
                    short_length=get_int(u, "SrtLen", 2),
                    medium_length=get_int(u, "MedLength", 5),
                    finish_length=get_int(u, "FinLen", 2),
                    small_area=get_int(u, "SmalArea", 5),
                    large_area=get_int(u, "LgArea", 5),
                    volume=get_int(u, "Volume", 4),
                    small_flow=get_int(u, "SmlFlow", 1),
                    medium_flow=get_int(u, "MdmFlow", 7),
                    large_flow=get_int(u, "LrgFlow", 2),
                    velocity=get_int(u, "Velocity", 2),
                    slope=get_int(u, "Slope", 3),
                    rain=get_int(u, "Rain", 1),
                    rain_depth=get_int(u, "Rain_Dept", 1),
                    infiltration=get_int(u, "Infl", 2),
                )

        rainfall_sources = []
        if site is not None:
            rm = site.find("RainfMngr")
            if rm is not None:
                ri = rm.find("RainfallItems")
                if ri is not None:
                    for tag in RAINFALL_SOURCE_TAGS:
                        for rs_elem in ri.findall(tag):
                            rainfall_sources.append(RainfallSource.from_xml(rs_elem))

        phases = {}
        if site is not None:
            phases_container = site.find("Phases")
            if phases_container is not None:
                for phase_elem in phases_container.findall("Phase"):
                    p = Phase.from_xml(phase_elem)
                    phases[p.label] = p

        return cls(
            filepath=filepath,
            author=author,
            units=units,
            db_ver_guid=db_ver_guid,
            phases=phases,
            rainfall_sources=rainfall_sources,
            _tree=tree,
            _root=root,
        )

    @classmethod
    def new(
        cls,
        region: str = "United States",
        product_version: str = "2026.4",
        user: str = "",
    ) -> IddxModel:
        """Create a new empty IddxModel."""
        from datetime import datetime

        root = Element("InfoDrainage")
        author_elem = Element("Author")
        author_elem.set("Product", "InfoDrainage")
        author_elem.set("Manufacturer", "Autodesk, Inc.")
        author_elem.set("Version", product_version)
        author_elem.set("User", user)
        now = datetime.now().isoformat()
        author_elem.set("Date", now)
        root.append(author_elem)

        db_guid = f"{datetime.now().strftime('%Y%m%d%H%M')}-{new_guid()}"
        site = Element("Site")
        site.set("DBVerGUID", db_guid)

        u = Element("Units")
        u.set("Region", region)
        for attr, val in [
            ("Depth", 5), ("FinLen", 2), ("SrtLen", 2), ("MedLength", 5),
            ("SmalArea", 5), ("LgArea", 5), ("Volume", 4), ("SmlFlow", 1),
            ("MdmFlow", 7), ("LrgFlow", 2), ("Velocity", 2), ("Viscosity", 9),
            ("Conc", 0), ("Slope", 3), ("Rain", 1), ("Rain_Dept", 1),
            ("Infl", 2), ("Evap", 1), ("Intensity_Flow", 0), ("Mass", 3),
            ("Load", 6), ("SmlTime", 1), ("MedTime", 0), ("LrgTime", 1),
            ("TimeFrmt", 1), ("DateFrmt", 1), ("Perc", 0),
        ]:
            set_int(u, attr, val)
        site.append(u)

        site.append(Element("Template"))
        rm = Element("RainfMngr")
        rm.append(Element("RainfallItems"))
        site.append(rm)

        hch = Element("HCH")
        hch.set("HeadTit", "Project")
        hch.set("SHeadTit", "Company Address")
        hch.set("ModDate", now)
        set_int(hch, "PageNum", 1)
        site.append(hch)

        ps = Element("PrintSettings")
        margin = Element("Margin")
        for side in ("Left", "Right", "Top", "Bottom"):
            set_int(margin, side, 100)
        ps.append(margin)
        site.append(ps)

        _add_default_display_settings(site)

        for tag in (
            "compSheets", "reportingSheet", "AudRep", "NumScheme",
            "ProfileCADOptions", "MHSCADOptions", "PlotSettings",
            "Polls", "StormAnalCriteria", "DryAnalCriteria", "Tables",
            "FlexReportData", "GISImportMap", "GISExportMap",
            "TextImportMap", "TextExportMap", "StormNetDesCrit",
            "FoulNetDesCrit", "FFData", "PartFamilies",
        ):
            site.append(Element(tag))

        lu = Element("LandUseObj")
        lu.set("Label", "Default LandUse")
        lu.set("GUID", new_guid())
        site.append(lu)

        st = Element("SoilTypeObj")
        st.set("Label", "Default SoilType")
        st.set("GUID", new_guid())
        site.append(st)

        site.append(Element("Bookmarks"))

        sl = Element("SiteLocation")
        for attr in ("SL_LocDet", "SL_SiteDet", "SL_ProjRef", "SL_ProjDets"):
            sl.set(attr, "")
        site.append(sl)

        site.append(Element("Phases"))
        root.append(site)

        tree = ET.ElementTree(root)

        return cls(
            author=AuthorInfo(
                product="InfoDrainage",
                manufacturer="Autodesk, Inc.",
                version=product_version,
                user=user,
                date=now,
            ),
            units=UnitSettings(region=region),
            db_ver_guid=db_guid,
            _tree=tree,
            _root=root,
        )

    # -- Phase management --------------------------------------------------

    def add_phase(self, phase: Phase) -> Phase:
        phase.index = len(self.phases)
        self.phases[phase.label] = phase
        return phase

    def create_phase(self, label: str, analyse: bool = True) -> Phase:
        phase = Phase(
            index=len(self.phases),
            label=label,
            analyse=analyse,
        )
        self.phases[label] = phase
        return phase

    def clone_phase(self, source_label: str, new_label: str) -> Phase:
        source = self.phases.get(source_label)
        if source is None:
            raise KeyError(f"Phase '{source_label}' not found")
        new_phase = source.clone(new_label)
        new_phase.index = len(self.phases)
        self.phases[new_label] = new_phase
        return new_phase

    def remove_phase(self, label: str) -> bool:
        if label in self.phases:
            del self.phases[label]
            for i, p in enumerate(self.phases.values()):
                p.index = i
            return True
        return False

    # -- Rainfall management -----------------------------------------------

    def add_rainfall_source(self, source: RainfallSource) -> RainfallSource:
        source.index = len(self.rainfall_sources)
        self.rainfall_sources.append(source)
        return source

    def find_rainfall_source(self, label: str) -> Optional[RainfallSource]:
        for rs in self.rainfall_sources:
            if rs.label == label:
                return rs
        return None

    # -- Summary -----------------------------------------------------------

    def summary(self) -> dict:
        return {
            "filepath": str(self.filepath) if self.filepath else None,
            "product_version": self.author.version,
            "region": self.units.region,
            "rainfall_sources": len(self.rainfall_sources),
            "phases": {label: phase.summary() for label, phase in self.phases.items()},
        }

    # -- Save --------------------------------------------------------------

    def save(self, filepath: Optional[str | Path] = None) -> Path:
        """Save the model to an .iddx file."""
        out_path = Path(filepath) if filepath else self.filepath
        if out_path is None:
            raise ValueError("No filepath specified for save")

        root = self._build_xml()
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(str(out_path), encoding="unicode", xml_declaration=False)

        self.filepath = out_path
        return out_path

    def _build_xml(self) -> Element:
        """Build the full XML tree from the current model state."""
        if self._root is not None:
            root = copy.deepcopy(self._root)
        else:
            root = Element("InfoDrainage")

        author_elem = root.find("Author")
        if author_elem is None:
            author_elem = Element("Author")
            root.insert(0, author_elem)
        author_elem.set("Product", self.author.product)
        author_elem.set("Manufacturer", self.author.manufacturer)
        author_elem.set("Version", self.author.version)
        author_elem.set("User", self.author.user)

        site = root.find("Site")
        if site is None:
            site = Element("Site")
            root.append(site)
        site.set("DBVerGUID", make_ver_guid())

        rm = site.find("RainfMngr")
        if rm is None:
            rm = Element("RainfMngr")
            site.append(rm)
        ri = rm.find("RainfallItems")
        if ri is None:
            ri = Element("RainfallItems")
            rm.append(ri)
        for tag in RAINFALL_SOURCE_TAGS:
            for old in list(ri.findall(tag)):
                ri.remove(old)
        for rs in self.rainfall_sources:
            ri.append(rs.to_xml())

        sac = site.find("StormAnalCriteria")
        if sac is not None and self.rainfall_sources:
            rs0 = self.rainfall_sources[0]
            rgp = sac.find("RainGuidPairs")
            if rgp is not None and len(list(rgp)) == 0:
                pair = Element("RainGuidPair")
                set_int(pair, "Index", 0)
                pair.set("rsGuid", rs0.guid)
                pair.set("verGuid", rs0.ver_guid)
                rgp.append(pair)

            strdet = sac.find("StrDet")
            if strdet is not None:
                stag = get_str(strdet, "STag")
                if not stag and rs0.storm_definitions:
                    dur = str(int(rs0.storm_definitions[0].duration_minutes))
                    strdet.set("STag", dur)
                    strdet.set("RainfallGuid", rs0.guid)

        phases_container = site.find("Phases")
        if phases_container is None:
            phases_container = Element("Phases")
            site.append(phases_container)
        for old_phase in list(phases_container.findall("Phase")):
            phases_container.remove(old_phase)
        for i, (label, phase) in enumerate(self.phases.items()):
            phases_container.append(phase.to_xml(index=i))

        return root

    def __repr__(self) -> str:
        n_phases = len(self.phases)
        n_rainfall = len(self.rainfall_sources)
        return (
            f"IddxModel(filepath={self.filepath}, "
            f"version={self.author.version!r}, "
            f"phases={n_phases}, rainfall_sources={n_rainfall})"
        )


def _add_default_display_settings(site: Element) -> None:
    """Add minimal DisplaySettings to a new site element."""
    ds = Element("DisplaySettings")
    ds.set("GridSize", "30.4800609601")
    ds.set("Text", "3.657607315212")
    ds.set("Icon", "9.14401828803")
    ds.set("Line", "2")
    set_bool(ds, "MainPlanView", True)
    set_int(ds, "JunctionTransparency", 20)
    set_bool(ds, "AllJunctionsTransparent", False)
    set_int(ds, "Font", 8)
    set_int(ds, "SummaryFont", 8)
    set_int(ds, "VertScl", 1)

    cs = Element("ColourSettings")
    scl = Element("ScreenColourList")
    scl.set("PlanBackground", "-14604240")
    scl.set("PlanGrid", "-4144960")
    scl.set("PlanInflow", "-16751616")
    scl.set("PlanInflowLabel", "-7278960")
    scl.set("PlanDrainageSystem", "-29696")
    scl.set("PlanJunction", "-4144960")
    scl.set("PlanConnection", "-16728065")
    scl.set("PlanConnectionLabel", "-16728065")
    scl.set("PlanSelectedItem", "-10496")
    pe = Element("PlanElevation")
    pe.set("Ramp", "5")
    pe.set("B", "0")
    pe.set("T", "46")
    pe.append(Element("Ext"))
    pe.append(Element("Ints"))
    scl.append(pe)
    pg = Element("PlanGeometry")
    scl.append(pg)
    cs.append(scl)
    ds.append(cs)

    lf = Element("LayerFlags")
    for attr in (
        "LFTerrain", "LFCad", "LFGis", "LFBkImage",
        "LFNFP", "LFInf", "LFDS", "LFJnc", "LFCon",
        "LFAnn", "LFLandUse", "LFSoilType", "LFMNode",
    ):
        set_bool(lf, attr, True)
    ds.append(lf)

    ds.append(Element("AnnoSettings"))
    site.append(ds)
