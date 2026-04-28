"""XML parsing utilities and helpers for .iddx files."""

import copy
import uuid
from datetime import datetime
from xml.etree.ElementTree import Element
from typing import Optional


class RawXmlBacked:
    """Mixin for dataclasses that round-trip through XML.

    Subclasses are expected to declare a ``_raw_element: Optional[Element]`` field
    (initialised to ``None`` and excluded from ``init`` / ``repr`` / ``compare``)
    that holds the originally-parsed Element. This lets ``to_xml`` deep-copy and
    patch the raw tree, preserving unknown XML children that the Python model
    doesn't explicitly mirror.
    """

    def _copy_raw(self) -> Optional[Element]:
        """Return a deep copy of the raw parsed element, or None if absent."""
        elem = getattr(self, "_raw_element", None)
        if elem is None:
            return None
        return copy.deepcopy(elem)


def new_guid() -> str:
    return str(uuid.uuid4())


def make_ver_guid() -> str:
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M")
    return f"{timestamp}-{new_guid()}"


def get_float(elem: Element, attr: str, default: float = 0.0) -> float:
    val = elem.get(attr)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def get_int(elem: Element, attr: str, default: int = 0) -> int:
    val = elem.get(attr)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def get_bool(elem: Element, attr: str, default: bool = False) -> bool:
    val = elem.get(attr)
    if val is None:
        return default
    return val.lower() == "true"


def get_str(elem: Element, attr: str, default: str = "") -> str:
    val = elem.get(attr)
    return val if val is not None else default


def set_float(elem: Element, attr: str, value: float) -> None:
    elem.set(attr, str(value))


def set_int(elem: Element, attr: str, value: int) -> None:
    elem.set(attr, str(value))


def set_bool(elem: Element, attr: str, value: bool) -> None:
    elem.set(attr, "True" if value else "False")


def find_or_create(parent: Element, tag: str) -> Element:
    """Find a child element or create it if missing."""
    child = parent.find(tag)
    if child is None:
        child = Element(tag)
        parent.append(child)
    return child


def parse_coordinate_2d(elem: Element) -> Optional[tuple[float, float]]:
    """Extract (X, Y) from a Coordinate2D element."""
    if elem is None:
        return None
    return (get_float(elem, "X"), get_float(elem, "Y"))


def make_coordinate_2d(x: float, y: float, index: Optional[int] = None) -> Element:
    """Create a Coordinate2D element."""
    elem = Element("Coordinate2D")
    elem.set("X", str(x))
    elem.set("Y", str(y))
    if index is not None:
        elem.set("Index", str(index))
    return elem


def parse_polygon(outline_details: Element) -> list[tuple[float, float]]:
    """Extract polygon vertices from a FreeFormOutlineDetails element."""
    coords = []
    coord2ds = outline_details.find("Coord2Ds")
    if coord2ds is None:
        return coords
    for coord in coord2ds.findall("Coordinate2D"):
        pt = parse_coordinate_2d(coord)
        if pt:
            coords.append(pt)
    return coords


def make_polygon_element(
    coords: list[tuple[float, float]], centre_line_locked: bool = False
) -> Element:
    """Create a FreeFormOutlineDetails element from polygon vertices."""
    outline = Element("FreeFormOutlineDetails")
    outline.set("CentreLineLocked", "True" if centre_line_locked else "False")
    cl = Element("CentreLine")
    outline.append(cl)
    coord2ds = Element("Coord2Ds")
    for i, (x, y) in enumerate(coords):
        coord2ds.append(make_coordinate_2d(x, y, index=i))
    outline.append(coord2ds)
    outline.append(Element("BaseCoords"))
    return outline
