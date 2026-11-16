"""Device tracker platform for the XPENG integration."""
from __future__ import annotations

import logging
import time

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .coordinator import XPengDataCoordinator
from .entity import XPengEntity
from .entity_layout import zone_only_enabled
from .zone_match import ZoneInfo, resolve_zone

_LOGGER = logging.getLogger(__name__)


def _zones(hass: HomeAssistant) -> list[ZoneInfo]:
    """Return every zone.* state as a ZoneInfo."""
    zones: list[ZoneInfo] = []
    for state in hass.states.async_all("zone"):
        attrs = state.attributes
        try:
            zones.append(
                (
                    state.entity_id,
                    str(attrs.get("friendly_name", state.name)),
                    float(attrs["latitude"]),
                    float(attrs["longitude"]),
                    float(attrs.get("radius", 100)),
                    bool(attrs.get("passive", False)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return zones


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up XPENG device tracker."""
    coordinator: XPengDataCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([XPengDeviceTracker(coordinator, entry)])


class XPengDeviceTracker(XPengEntity, TrackerEntity):
    """Represent the XPENG vehicle location as a device tracker."""

    _attr_has_entity_name = True
    _attr_translation_key = "location"
    _attr_icon = "mdi:car"

    def __init__(
        self, coordinator: XPengDataCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"xpeng_{self._vin}_location"

    async def async_added_to_hass(self) -> None:
        """Follow zone edits, since the reported zone depends on them."""
        await super().async_added_to_hass()

        @callback
        def _zone_changed(event: Event) -> None:
            self.async_write_ha_state()

        zone_ids = [s.entity_id for s in self.hass.states.async_all("zone")]
        if zone_ids:
            self.async_on_remove(
                async_track_state_change_event(self.hass, zone_ids, _zone_changed)
            )

    @property
    def location_name(self) -> str | None:
        """Return the zone name when only the zone is reported."""
        if not zone_only_enabled(self._entry):
            return None
        fix = self.coordinator.gps_fix.position
        if not fix:
            return None
        return resolve_zone(fix[0], fix[1], _zones(self.hass))

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude of the last position that was a real fix."""
        if zone_only_enabled(self._entry):
            return None
        fix = self.coordinator.gps_fix.position
        return fix[0] if fix else None

    @property
    def longitude(self) -> float | None:
        """Return longitude of the last position that was a real fix."""
        if zone_only_enabled(self._entry):
            return None
        fix = self.coordinator.gps_fix.position
        return fix[1] if fix else None

    @property
    def course(self) -> float | None:
        """Return the direction the car faces, in degrees, or None.

        Home Assistant's map card rotates the marker from ``course``; ``bearing``
        keeps the same raw value as an attribute for existing templates. None
        when the car has never reported an angle, so a number cannot be drawn as
        a heading the car did not send.
        """
        if zone_only_enabled(self._entry):
            return None
        angle = self._get_nested_value("msg_content.interval.drive.angle")
        try:
            return None if angle is None else float(angle)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, str | float | bool | None]:
        """Return extra attributes.

        ``coord_valid`` and ``fix_age_s`` are the point of this entity: the car
        can report coordinates that are its last known position rather than a
        current fix (``interval.drive.coordValid`` false), and a position whose
        age is not visible is what made "the car is still at home" look like a
        lost GPS. Age is None when no valid fix has been seen yet this session.
        """
        age = self.coordinator.gps_fix.age_seconds(time.time())
        age_s = None if age is None else round(age)
        if zone_only_enabled(self._entry):
            return {
                "coord_valid": self.coordinator.gps_fix.coord_valid,
                "fix_age_s": age_s,
            }
        speed_raw = self._get_nested_value("msg_content.interval.drive.speed")
        angle = self._get_nested_value("msg_content.interval.drive.angle")
        coord_type = self._get_nested_value("msg_content.interval.drive.coordType")

        speed = None
        if speed_raw is not None:
            try:
                speed = round(float(speed_raw), 1)
            except (ValueError, TypeError):
                pass

        return {
            "speed": speed,
            "bearing": angle,
            "coord_type": coord_type,
            "coord_valid": self.coordinator.gps_fix.coord_valid,
            "fix_age_s": age_s,
        }
