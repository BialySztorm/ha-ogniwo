"""Tests for setting up and polling a controller."""

from unittest.mock import patch

import aiohttp
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.ogniwo.const import DOMAIN

from . import load_fixture
from .conftest import BASE, MAC


async def test_setup_registers_controller_and_radio_sensor(hass, loaded):
    devices = dr.async_get(hass)

    boiler = devices.async_get_device_by_identifier((DOMAIN, MAC), loaded.entry_id)
    sensor = devices.async_get_device_by_identifier((DOMAIN, f"{MAC}_85"), loaded.entry_id)

    assert loaded.state is ConfigEntryState.LOADED
    assert boiler.name == "Boiler"
    assert boiler.manufacturer == "ELEKTRO-SYSTEM"
    assert boiler.model == "pello_D"
    assert boiler.sw_version == "1.1.38.58"
    assert boiler.configuration_url == BASE
    assert sensor.name == "Boiler Zone 1 temperature"
    assert sensor.model == "BT5BV3"
    assert sensor.via_device_id == boiler.id


async def test_setup_and_polling_never_write_to_the_controller(hass, controller, loaded):
    await loaded.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert controller.writes == []


async def test_unload(hass, loaded):
    assert await hass.config_entries.async_unload(loaded.entry_id)

    assert loaded.state is ConfigEntryState.NOT_LOADED


async def test_unreachable_controller_is_retried(hass, aioclient_mock, entry):
    aioclient_mock.get(f"{BASE}/info.cgi", exc=aiohttp.ClientConnectionError("down"))

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_rejected_credentials_start_reauth(hass, aioclient_mock, entry):
    aioclient_mock.get(f"{BASE}/info.cgi", text=load_fixture("info.xml"))
    aioclient_mock.get(f"{BASE}/config/hardware.xml", status=401)

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert [
        flow["context"]["source"] for flow in entry.async_get_active_flows(hass, {SOURCE_REAUTH})
    ]


async def test_entities_become_unavailable_when_polling_fails(hass, aioclient_mock, loaded):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", exc=TimeoutError())

    await loaded.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.boiler_water_temperature").state == "unavailable"


async def test_credentials_rejected_while_polling_start_reauth(hass, aioclient_mock, loaded):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", status=401)

    await loaded.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert list(loaded.async_get_active_flows(hass, {SOURCE_REAUTH}))


async def test_firmware_change_reloads_the_entry(hass, controller, loaded):
    controller.set("device_soft_version", "1.1.39.1")

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        await loaded.runtime_data.async_refresh()

    reload.assert_called_once_with(loaded.entry_id)


async def test_read_only_mode_swaps_controls_for_sensors_and_back(hass, controller, loaded):
    hass.config_entries.async_update_entry(loaded, options={"read_only": True})
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()

    assert loaded.runtime_data.read_only
    assert hass.states.get("number.boiler_setpoint") is None
    assert hass.states.get("button.boiler_acknowledge_alarms") is None
    assert hass.states.get("sensor.boiler_setpoint").state == "65"
    assert hass.states.get("sensor.boiler_season_mode").state == "auto_summer"

    hass.config_entries.async_update_entry(loaded, options={"read_only": False})
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("number.boiler_setpoint").state == "65"
    assert hass.states.get("sensor.boiler_setpoint") is None


async def test_entity_of_a_node_that_lost_its_pairing_is_kept(hass, controller, loaded):
    controller.set("s", "0", vid=85)

    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert registry.async_get("sensor.boiler_zone_1_temperature_temperature") is not None
