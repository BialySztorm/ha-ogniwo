"""Diagnostics of the Ogniwo integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import OgniwoConfigEntry

REDACT_CONFIG = {CONF_HOST, CONF_USERNAME, CONF_PASSWORD}
REDACT_VALUES = {
    "device_sn",
    "device_id",
    "device_name",
    "device_location",
    "eth_mac",
    "eth_ip",
    "eth_ip_ro",
    "eth_gate",
    "eth_gate_ro",
    "eth_mask",
    "eth_mask_ro",
    "localtimezone",
    "name",
}
# Weekly schedules reveal when the house is occupied.
SCHEDULE_SUFFIXES = ("_prog", "tbl")


def _values(values: dict[str, str]) -> dict[str, str]:
    kept = {tid: value for tid, value in values.items() if not tid.endswith(SCHEDULE_SUFFIXES)}
    return async_redact_data(kept, REDACT_VALUES)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OgniwoConfigEntry
) -> dict[str, Any]:
    """Return the raw register values with identifying data removed."""
    coordinator = entry.runtime_data
    info = coordinator.info
    return {
        "config": async_redact_data(dict(entry.data), REDACT_CONFIG),
        "options": dict(entry.options),
        "controller": {
            "hardware_type": info.hardware_type,
            "hardware_version": info.hardware_version,
            "software_version": info.software_version,
            "dictionary_version": coordinator.dictionary.version,
            "access_level": coordinator.access_level,
        },
        "entities": len(coordinator.specs),
        "values": {
            str(vid): {
                "timestamp": device.timestamp,
                "values": _values(dict(device.values)),
            }
            for vid, device in coordinator.data.devices.items()
        },
    }
