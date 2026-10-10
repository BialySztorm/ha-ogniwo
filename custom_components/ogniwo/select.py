"""Enumerated settings of the Ogniwo integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .catalog import EntitySpec
from .coordinator import OgniwoConfigEntry, OgniwoCoordinator
from .entity import OgniwoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OgniwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a select for every enumerated setting the account may change."""
    coordinator = entry.runtime_data
    async_add_entities(
        OgniwoSelect(coordinator, spec) for spec in coordinator.specs_for(Platform.SELECT)
    )


class OgniwoSelect(OgniwoEntity, SelectEntity):
    """An enum register that can be changed."""

    def __init__(self, coordinator: OgniwoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)
        self._states = self.option_states()
        self._attr_options = list(self._states.values())

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        raw = self.raw
        return None if raw is None else self._states.get(raw)

    async def async_select_option(self, option: str) -> None:
        """Write the selected option to the controller."""
        option_id = next((raw for raw, state in self._states.items() if state == option), None)
        if option_id is None:
            raise HomeAssistantError(f"Unknown option: {option}")
        await self.coordinator.async_write(self._vid, self._register.tid, option_id)
