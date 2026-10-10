"""Polling of a Ogniwo controller."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OgniwoClient
from .catalog import EntitySpec, build_specs
from .const import (
    ACCESS_LEVEL_USER,
    CONF_READ_ONLY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAIN_VID,
    STALE_AFTER,
)
from .errors import OgniwoAuthError, OgniwoError
from .models import ControllerInfo, Dictionary, Snapshot

_LOGGER = logging.getLogger(__name__)

type OgniwoConfigEntry = ConfigEntry[OgniwoCoordinator]

REGISTER_ACCESS_LEVEL = "accesslevel"
REGISTER_FIRMWARE = "device_soft_version"

# Device names prefix entity ids, which stay English whatever the UI language is.
NODE_NAME_LANGUAGE = "en"


class OgniwoCoordinator(DataUpdateCoordinator[Snapshot]):
    """Reads all registers of a controller in one request per interval."""

    config_entry: OgniwoConfigEntry
    info: ControllerInfo
    dictionary: Dictionary

    def __init__(self, hass: HomeAssistant, entry: OgniwoConfigEntry, client: OgniwoClient) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.read_only: bool = entry.options.get(CONF_READ_ONLY, False)
        self.language = hass.config.language
        self.specs: list[EntitySpec] = []
        self.main_device_id: str | None = None
        self._firmware: str | None = None

    async def _async_setup(self) -> None:
        try:
            self.info = await self.client.async_get_info()
            self.dictionary = await self.client.async_get_dictionary()
        except OgniwoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OgniwoError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_update_data(self) -> Snapshot:
        try:
            snapshot = await self.client.async_get_snapshot()
        except OgniwoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OgniwoError as err:
            raise UpdateFailed(str(err)) from err

        firmware = snapshot.value(MAIN_VID, REGISTER_FIRMWARE)
        if self._firmware and firmware and firmware != self._firmware:
            # New firmware may bring a different register dictionary.
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        self._firmware = firmware or self._firmware
        return snapshot

    @property
    def access_level(self) -> int:
        """Access level of the configured account; lower means more privileged."""
        try:
            return int(self.data.value(MAIN_VID, REGISTER_ACCESS_LEVEL) or "")
        except ValueError:
            return ACCESS_LEVEL_USER

    def prepare_specs(self) -> None:
        """Decide once per setup which entities exist."""
        self.specs = build_specs(self.dictionary, self.data, self.access_level, self.read_only)

    def unique_id(self, vid: int, key: str) -> str:
        """Build the unique id of an entity of this controller."""
        return f"{self.info.mac}_{vid}_{key}"

    def specs_for(self, platform: Platform) -> list[EntitySpec]:
        """Return the entities of one platform."""
        return [spec for spec in self.specs if spec.platform is platform]

    def is_stale(self, vid: int) -> bool:
        """Tell whether a radio node stopped reporting."""
        if vid == MAIN_VID:
            return False
        device = self.data.devices.get(vid)
        if device is None:
            return True
        return self.data.controller_time - device.timestamp > STALE_AFTER.total_seconds()

    async def async_write(self, vid: int, tid: str, value: str) -> None:
        """Change a register on the controller and read the values back."""
        if self.read_only:
            raise HomeAssistantError("The integration is configured as read-only")
        try:
            await self.client.async_set_register(vid, tid, value)
        except OgniwoAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"Could not change {tid}: {err}") from err
        except OgniwoError as err:
            raise HomeAssistantError(f"Could not change {tid}: {err}") from err
        # Not async_request_refresh: its cooldown would leave the old value on screen
        # for several seconds after a second change in a row.
        await self.async_refresh()

    def device_info(self, vid: int) -> DeviceInfo:
        """Describe the controller or one of its radio nodes for the device registry."""
        title = self.config_entry.title
        if vid == MAIN_VID:
            return DeviceInfo(
                identifiers={(DOMAIN, self.info.mac)},
                name=title,
                manufacturer=self.info.company or None,
                model=self.info.hardware_type or None,
                hw_version=self.info.hardware_version or None,
                sw_version=self._firmware or self.info.software_version or None,
                configuration_url=self.client.base_url,
            )

        values = self.data.devices[vid].values
        vdev = self.dictionary.vdevs.get(vid)
        name = values.get("name") or (vdev.name(NODE_NAME_LANGUAGE) if vdev else None) or str(vid)
        info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.info.mac}_{vid}")},
            name=f"{title} {name}",
            manufacturer=self.info.company or None,
            model=values.get("t") or None,
            sw_version=values.get("v") or None,
        )
        if self.main_device_id is not None:
            info["via_device_id"] = self.main_device_id
        return info
