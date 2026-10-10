"""Tests for the config, reauth and options flows."""

from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ogniwo.const import DOMAIN

from . import load_fixture
from .conftest import BASE, HOST, LEGACY_URL, MAC, serve_no_legacy

USER_INPUT = {CONF_HOST: HOST, CONF_USERNAME: "root", CONF_PASSWORD: "example"}


@pytest.fixture(autouse=True)
def skip_setup():
    with patch("custom_components.ogniwo.async_setup_entry", return_value=True):
        yield


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_user_flow_creates_entry_named_by_the_controller(hass, controller):
    result = await start(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Testowy"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == MAC


async def test_user_flow_accepts_a_custom_name(hass, controller):
    result = await start(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_NAME: "Cellar Boiler"}
    )

    assert result["title"] == "Cellar Boiler"
    assert CONF_NAME not in result["data"]


@pytest.mark.parametrize(
    ("endpoint", "response", "error"),
    [
        ("syncvalues.cgi", {"status": 401}, "invalid_auth"),
        ("syncvalues.cgi", {"status": 403}, "invalid_auth"),
        ("info.cgi", {"exc": aiohttp.ClientConnectionError("down")}, "cannot_connect"),
        ("info.cgi", {"status": 500}, "cannot_connect"),
        ("info.cgi", {"text": "<cmd/>"}, "unknown"),
        ("syncvalues.cgi", {"text": "garbage"}, "unknown"),
    ],
)
async def test_user_flow_reports_errors_and_recovers(
    hass, aioclient_mock, controller, endpoint, response, error
):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/{endpoint}", **response)
    aioclient_mock.get(f"{BASE}/info.cgi", text=load_fixture("info.xml"))
    serve_no_legacy(aioclient_mock)
    result = await start(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    controller.serve()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    "host", ["http://192.0.2.10", "192.0.2.10:8080", "root:secret@192.0.2.10", "192.0.2.10/x"]
)
async def test_user_flow_rejects_a_host_that_is_not_a_host(hass, caplog, host):
    result = await start(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: host}
    )

    assert result["errors"] == {"base": "invalid_host"}
    assert "secret" not in caplog.text


async def test_user_flow_updates_the_address_of_a_known_controller(hass, aioclient_mock, entry):
    moved = "192.0.2.20"
    aioclient_mock.get(f"http://{moved}/info.cgi", text=load_fixture("info.xml"))
    aioclient_mock.get(f"http://{moved}/syncvalues.cgi", text=load_fixture("syncvalues.txt"))
    result = await start(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: moved}
    )

    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == moved


async def test_user_flow_aborts_for_a_known_controller(hass, controller, entry):
    result = await start(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_credentials(hass, controller, entry):
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "new"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {CONF_HOST: HOST, CONF_USERNAME: "admin", CONF_PASSWORD: "new"}


async def test_reauth_keeps_asking_while_credentials_are_wrong(hass, aioclient_mock, entry):
    aioclient_mock.get(f"{BASE}/info.cgi", text=load_fixture("info.xml"))
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", status=401)
    result = await entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "root", CONF_PASSWORD: "wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


OTHER_CONTROLLER = load_fixture("info.xml").replace("aabbccddeeff", "112233445566")


async def test_reauth_refuses_a_different_controller(hass, aioclient_mock, controller, entry):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/info.cgi", text=OTHER_CONTROLLER)
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", text=load_fixture("syncvalues.txt"))
    result = await entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "root", CONF_PASSWORD: "example"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_reconfigure_changes_the_address(hass, aioclient_mock, entry):
    moved = "192.0.2.20"
    aioclient_mock.get(f"http://{moved}/info.cgi", text=load_fixture("info.xml"))
    aioclient_mock.get(f"http://{moved}/syncvalues.cgi", text=load_fixture("syncvalues.txt"))
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: moved}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == moved


async def test_reconfigure_refuses_a_different_controller(hass, aioclient_mock, entry):
    aioclient_mock.get(f"{BASE}/info.cgi", text=OTHER_CONTROLLER)
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", text=load_fixture("syncvalues.txt"))
    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_HOST] == HOST


async def test_reconfigure_reports_errors(hass, aioclient_mock, entry):
    aioclient_mock.get(f"{BASE}/info.cgi", exc=aiohttp.ClientConnectionError("down"))
    serve_no_legacy(aioclient_mock)
    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize(
    ("endpoint", "response"),
    [
        ("info.cgi", {"status": 404}),
        # Firmware that serves a panel but no register API at all.
        ("info.cgi", {"text": "<html>Login</html>"}),
    ],
)
async def test_user_flow_recognises_a_legacy_only_controller(
    hass, aioclient_mock, endpoint, response
):
    aioclient_mock.get(f"{BASE}/{endpoint}", **response)
    aioclient_mock.get(LEGACY_URL, text="[2,1,0,6,0,0,76,0]")
    result = await start(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "legacy_api"}


async def test_options_flow_stores_interval_and_read_only(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 60, "read_only": True}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval": 60, "read_only": True}


async def test_options_flow_rejects_too_short_interval(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises(Exception, match="scan_interval"):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 1, "read_only": False}
        )
