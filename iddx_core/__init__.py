"""iddx_core: Python library for reading, writing, and manipulating InfoDrainage .iddx files."""

from .model import IddxModel, AuthorInfo, UnitSettings
from .phase import Phase
from .nodes import Catchment, Junction, DrainageSystem, OutletDetail, ToCDetails, SCSDetails
from .connections import Connection, PipeConnection
from .rainfall import RainfallSource, StormEvent, HyetographItem
from .results import (
    ResultsReader, TimeSeries, NodeSummary, LinkSummary,
    ScenarioResult, ScenarioComparison,
    find_results, load_results, build_label_map,
)
from .enums import (
    RunoffMethod,
    JunctionType,
    JunctionShape,
    ConnectionType,
    OutletType,
    PhaseType,
    DrainageSystemType,
    IAType,
    ToCMethod,
)
from .exceptions import (
    IddxError,
    IddxParseError,
    IddxValidationError,
    ResultsError,
    ElementNotFoundError,
)

__version__ = "0.4.0"
__all__ = [
    "IddxModel",
    "AuthorInfo",
    "UnitSettings",
    "Phase",
    "Catchment",
    "Junction",
    "DrainageSystem",
    "OutletDetail",
    "ToCDetails",
    "SCSDetails",
    "Connection",
    "PipeConnection",
    "RainfallSource",
    "StormEvent",
    "HyetographItem",
    "ResultsReader",
    "TimeSeries",
    "NodeSummary",
    "LinkSummary",
    "ScenarioResult",
    "ScenarioComparison",
    "find_results",
    "load_results",
    "build_label_map",
    "RunoffMethod",
    "JunctionType",
    "JunctionShape",
    "ConnectionType",
    "OutletType",
    "PhaseType",
    "DrainageSystemType",
    "IAType",
    "ToCMethod",
    "IddxError",
    "IddxParseError",
    "IddxValidationError",
    "ResultsError",
    "ElementNotFoundError",
]
