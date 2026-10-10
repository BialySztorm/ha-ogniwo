"""Ogniwo pellet boiler controller integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OgniwoClient
from .catalog import CONTROL_PLATFORMS
from .const import MAIN_VID
from .coordinator import OgniwoConfigEntry, OgniwoCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: OgniwoConfigEntry) -> bool:
    """Set up a controller from a config entry."""
    client = OgniwoClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = OgniwoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    coordinator.prepare_specs()
    entry.runtime_data = coordinator

    # Radio nodes link to the controller by its registry id, so it has to exist first.
    controller = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **coordinator.device_info(MAIN_VID)
    )
    coordinator.main_device_id = controller.id
    _async_remove_stale_entities(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


@callback
def _async_remove_stale_entities(
    hass: HomeAssistant, entry: OgniwoConfigEntry, coordinator: OgniwoCoordinator
) -> None:
    """Drop entities replaced by another platform, e.g. settings after going read-only.

    An entity that merely stopped being reported (a radio node that lost its pairing)
    is kept, so its history and customisations survive until it comes back.
    """
    platforms = {
        coordinator.unique_id(spec.vid, spec.register.tid): spec.platform
        for spec in coordinator.specs
    }
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        platform = platforms.get(entity.unique_id)
        replaced = platform is not None and platform != entity.domain
        withdrawn = platform is None and entity.domain in CONTROL_PLATFORMS
        if replaced or withdrawn:
            registry.async_remove(entity.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: OgniwoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
