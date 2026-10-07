"""Canonical powertrain codes used by vehicle data and cost calculations."""

from collections.abc import Mapping

ICE_GASOLINE = "ICE_GASOLINE"
ICE_DIESEL = "ICE_DIESEL"
HEV = "HEV"
PHEV = "PHEV"
BEV = "BEV"

VALID_POWERTRAINS = frozenset({ICE_GASOLINE, ICE_DIESEL, HEV, PHEV, BEV})

POWERTRAIN_LABELS: Mapping[str, str] = {
    ICE_GASOLINE: "汽油車",
    ICE_DIESEL: "柴油車",
    HEV: "油電車 HEV",
    PHEV: "插電式油電 PHEV",
    BEV: "純電車 BEV",
}

_ALIASES = {
    "ice_gasoline": ICE_GASOLINE, "gasoline": ICE_GASOLINE, "汽油": ICE_GASOLINE, "汽油車": ICE_GASOLINE,
    "油車": ICE_GASOLINE, "ice_diesel": ICE_DIESEL, "diesel": ICE_DIESEL, "柴油": ICE_DIESEL, "柴油車": ICE_DIESEL,
    "hev": HEV, "hybrid": HEV, "油電": HEV, "油電車": HEV, "油電混合": HEV, "油電複合": HEV,
    "phev": PHEV, "plug-in hybrid": PHEV, "插電油電": PHEV, "插電式油電": PHEV,
    "插電混合": PHEV, "插電式油電車": PHEV,
    "bev": BEV, "ev": BEV, "electric": BEV, "battery electric": BEV, "電": BEV,
    "電車": BEV, "電動": BEV, "純電": BEV, "純電車": BEV, "電動車": BEV,
}


def normalize_powertrain(value: str) -> str | None:
    cleaned = value.strip().replace("　", " ").lower()
    if value.strip().upper() in VALID_POWERTRAINS:
        return value.strip().upper()
    return _ALIASES.get(cleaned)


def parse_powertrain(value: str) -> dict[str, str | float] | None:
    """Parse a user-facing drivetrain answer into a stable intent payload."""
    powertrain = normalize_powertrain(value)
    if powertrain is None:
        return None
    return {"intent": "select_powertrain", "powertrain": powertrain, "confidence": 0.95}
