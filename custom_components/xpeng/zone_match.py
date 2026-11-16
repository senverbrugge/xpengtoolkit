"""Resolve a position to the Home Assistant zone state, without Home Assistant."""
from __future__ import annotations

from collections.abc import Iterable
from math import asin, cos, radians, sin, sqrt

# (entity_id, friendly name, latitude, longitude, radius in metres, passive)
ZoneInfo = tuple[str, str, float, float, float, bool]

_EARTH_RADIUS_M = 6371000.0


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle (haversine) distance in metres."""
    p1, p2 = radians(lat1), radians(lat2)
    a = (
        sin((p2 - p1) / 2) ** 2
        + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * asin(sqrt(a))


def resolve_zone(
    latitude: float | None, longitude: float | None, zones: Iterable[ZoneInfo]
) -> str | None:
    """Return "home", a zone's friendly name or "not_home"; None for an unusable fix."""
    if latitude is None or longitude is None or (latitude == 0 and longitude == 0):
        return None
    best: tuple[float, float, str] | None = None
    for entity_id, name, zlat, zlon, radius, passive in zones:
        if passive:
            continue
        distance = _distance_m(latitude, longitude, zlat, zlon)
        if distance >= radius:
            continue
        if best is None or (distance, radius) < best[:2]:
            best = (distance, radius, "home" if entity_id == "zone.home" else name)
    return "not_home" if best is None else best[2]
