"""Sensors of the Ogniwo integration."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .catalog import NUMERIC_TYPES, TYPE_ENUM, TYPE_TIMESTAMP, EntitySpec
from .coordinator import OgniwoConfigEntry, OgniwoCoordinator
from .entity import OgniwoEntity, to_number


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OgniwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a sensor for every readable register."""
    coordinator = entry.runtime_data
    async_add_entities(
        OgniwoSensor(coordinator, spec) for spec in coordinator.specs_for(Platform.SENSOR)
    )


def to_datetime(raw: str, resolution: int | None = None) -> datetime | None:
    """Convert a unix time register to a datetime; zero means the event never happened."""
    seconds = to_number(raw)
    if not seconds:
        return None
    if resolution:
        seconds = round(seconds / resolution) * resolution
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


class OgniwoSensor(OgniwoEntity, SensorEntity):
    """A register shown as a sensor."""

    def __init__(self, coordinator: OgniwoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)
        register, curated = spec.register, spec.curated
        self._states: dict[str, str] = {}

        if register.type == TYPE_ENUM:
            self._states = self.option_states()
            if self._states:
                self._attr_device_class = SensorDeviceClass.ENUM
                self._attr_options = list(self._states.values())
            return

        if register.type == TYPE_TIMESTAMP:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            return

        if register.type not in NUMERIC_TYPES:
            return

        self._attr_native_unit_of_measurement = self.unit
        self._attr_suggested_display_precision = register.precision
        if curated is not None:
            self._attr_device_class = curated.device_class
            self._attr_state_class = curated.state_class
            self._attr_suggested_unit_of_measurement = curated.suggested_unit
        elif self.unit:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            # Most registers of an unknown controller are temperatures; the unit the
            # dictionary gives is enough to present them as such.
            if self.unit == UnitOfTemperature.CELSIUS:
                self._attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def native_value(self) -> str | float | int | datetime | None:
        """Return the register value in the form its type calls for."""
        raw = self.raw
        if raw is None:
            return None
        register_type = self._register.type
        if register_type == TYPE_ENUM:
            # An id missing from the dictionary would not be a valid enum state.
            return self._states.get(raw) if self._states else raw
        if register_type == TYPE_TIMESTAMP:
            curated = self._spec.curated
            return to_datetime(raw, curated.resolution if curated else None)
        if register_type in NUMERIC_TYPES:
            return to_number(raw)
        return raw
