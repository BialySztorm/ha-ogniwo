"""Binary sensors of the Ogniwo integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .catalog import TYPE_ALARM, EntitySpec
from .const import MAIN_VID
from .coordinator import OgniwoConfigEntry, OgniwoCoordinator
from .entity import OgniwoEntity, to_number
from .models import RegisterDef

ALARM_SUMMARY_KEY = "alarm"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OgniwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create binary sensors for outputs, inputs and alarms."""
    coordinator = entry.runtime_data
    specs = coordinator.specs_for(Platform.BINARY_SENSOR)
    alarms = [spec for spec in specs if spec.register.type == TYPE_ALARM]
    entities: list[BinarySensorEntity] = [
        OgniwoAlarm(coordinator, spec)
        if spec.register.type == TYPE_ALARM
        else OgniwoBinarySensor(coordinator, spec)
        for spec in specs
    ]
    entities.append(OgniwoAlarmSummary(coordinator, alarms))
    async_add_entities(entities)


def alarm_messages(register: RegisterDef, raw: str | None, language: str) -> list[str]:
    """Decode an alarm bit mask into the messages of the bits that are set."""
    mask = to_number(raw)
    if not isinstance(mask, int) or mask == 0:
        return []
    messages = [
        option.label(language)
        for option in register.options
        if option.id.isdigit() and mask & int(option.id)
    ]
    return messages or [str(mask)]


class OgniwoBinarySensor(OgniwoEntity, BinarySensorEntity):
    """An on/off register: a power output or a binary input."""

    def __init__(self, coordinator: OgniwoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)
        if spec.curated is not None:
            self._attr_device_class = spec.curated.device_class

    @property
    def is_on(self) -> bool | None:
        """Return True for any non-zero value; some outputs report several active states."""
        value = to_number(self.raw)
        return None if value is None else value != 0


class OgniwoAlarm(OgniwoEntity, BinarySensorEntity):
    """An alarm register: a bit mask of active alarm conditions."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool | None:
        """Return True when any alarm bit is set."""
        value = to_number(self.raw)
        return None if value is None else value != 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Describe the alarm conditions that are active."""
        return {"messages": alarm_messages(self._register, self.raw, self._language)}


class OgniwoAlarmSummary(CoordinatorEntity[OgniwoCoordinator], BinarySensorEntity):
    """Tells whether any alarm of the controller or its radio nodes is active."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = ALARM_SUMMARY_KEY

    def __init__(self, coordinator: OgniwoCoordinator, alarms: list[EntitySpec]) -> None:
        super().__init__(coordinator)
        self._alarms = alarms
        self._attr_unique_id = coordinator.unique_id(MAIN_VID, ALARM_SUMMARY_KEY)
        self._attr_device_info = coordinator.device_info(MAIN_VID)

    @property
    def suggested_object_id(self) -> str | None:
        """Keep the entity id in English."""
        return ALARM_SUMMARY_KEY

    def _active(self) -> list[str]:
        language = self.coordinator.language
        active: list[str] = []
        for spec in self._alarms:
            raw = self.coordinator.data.value(spec.vid, spec.register.tid)
            name = spec.register.name(language)
            active.extend(
                f"{name}: {message}" for message in alarm_messages(spec.register, raw, language)
            )
        return active

    @property
    def is_on(self) -> bool:
        """Return True when at least one alarm is active."""
        return bool(self._active())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """List the active alarms."""
        return {"active": self._active()}
