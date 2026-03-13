"""Enumeration values used throughout the InfoDrainage .iddx format."""

from enum import IntEnum


class RunoffMethod(IntEnum):
    RATIONAL = 0
    RAFTS = 1
    SCS_CURVE_NUMBER = 2
    SWMM = 3
    WALLINGFORD = 4
    GREEN_AMPT = 5
    HORTON = 6
    INITIAL_LOSS_PROP_LOSS = 7
    STATIC = 8
    EXTENDED_RATIONAL = 9
    FOUL = 11


class JunctionType(IntEnum):
    MANHOLE = 0
    STRUCTURE = 1


class JunctionShape(IntEnum):
    CIRCULAR = 0
    RECTANGULAR = 1


class ConnectionType(IntEnum):
    CIRCULAR_PIPE = 2
    BOX_CULVERT = 3
    TRAPEZOIDAL_CHANNEL = 4
    TRIANGULAR_CHANNEL = 5
    CUSTOM_BYPASS = 7
    ELLIPSE_CULVERT = 8


CONNECTION_ELEMENTS = {
    ConnectionType.CIRCULAR_PIPE: "PipeCon",
    ConnectionType.TRAPEZOIDAL_CHANNEL: "TrapChan",
    ConnectionType.TRIANGULAR_CHANNEL: "TriChan",
    ConnectionType.CUSTOM_BYPASS: "CustomCon",
}

ELEMENT_TO_CONNECTION_TYPE = {v: k for k, v in CONNECTION_ELEMENTS.items()}

ALL_CONNECTION_TAGS = ("PipeCon", "TrapChan", "TriChan", "CustomCon")


class OutletType(IntEnum):
    FLOW_CONTROL = 0
    COMPLEX = 7
    ORIFICE = 8
    PUMP = 9
    WEIR = 12
    FREE_OUTLET = 13


class PhaseType(IntEnum):
    STORM = 0
    FOUL = 1


class ToCMethod(IntEnum):
    USER_MANUAL = 0
    FRIEND_EQUATION = 1
    KIRPICH = 2


class IAType(IntEnum):
    DEPTH = 0
    FRACTION_OF_S = 1


class HydrologicCondition(IntEnum):
    POOR = 0
    FAIR = 1
    GOOD = 2


class SoilGroup(IntEnum):
    A = 0
    B = 1
    C = 2
    D = 3


class DrainageSystemType(IntEnum):
    POND = 0
    SWALE = 1
    BIORETENTION = 2
    POROUS_PAVEMENT = 3
    CHAMBER = 4
    TANK = 5


DRAINAGE_SYSTEM_ELEMENTS = {
    DrainageSystemType.POND: "PondDSys",
    DrainageSystemType.SWALE: "SwaleDraSys",
    DrainageSystemType.BIORETENTION: "BioDraSys",
    DrainageSystemType.POROUS_PAVEMENT: "PorPavDSys",
    DrainageSystemType.CHAMBER: "ChamberDS",
    DrainageSystemType.TANK: "TankDSys",
}

ELEMENT_TO_DSYS_TYPE = {v: k for k, v in DRAINAGE_SYSTEM_ELEMENTS.items()}

ALL_DSYS_TAGS = tuple(DRAINAGE_SYSTEM_ELEMENTS.values())


class Hec22InletType(IntEnum):
    GRATE = 0
    CURB = 1
    COMBINATION = 2
    SLOTTED = 3


class InletCapacityType(IntEnum):
    NONE = 0
    LOW_HIGH_FLOW = 1
    RATED_BY_FLOW = 2
    HEC_22 = 3


class InletLocation(IntEnum):
    ON_GRADE = 0
    IN_SAG = 1
