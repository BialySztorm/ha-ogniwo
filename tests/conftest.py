"""Shared fixtures: a mocked controller and a config entry pointing at it."""

import re

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ogniwo.const import DOMAIN

from . import load_fixture

HOST = "192.0.2.10"
BASE = f"http://{HOST}"
MAC = "aabbccddeeff"

# The probe the config flow sends to tell a legacy controller from an unreachable one.
LEGACY_URL = f"{BASE}/?com=02010006000000006103"


def serve_no_legacy(aioclient_mock) -> None:
    """Answer the legacy byte-frame probe the way a register API controller does."""
    aioclient_mock.get(LEGACY_URL, status=404)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components."""


def with_value(text: str, tid: str, value: str, vid: int = 0) -> str:
    """Return the syncvalues response with one register of one device slot changed."""
    lines = text.split("\r")
    index = next(i for i, line in enumerate(lines) if line.startswith(f"{vid};"))
    lines[index], count = re.subn(rf";{tid}:[^;]*;", f";{tid}:{value};", lines[index])
    assert count == 1, f"register {tid} not found on device {vid}"
    return "\r".join(lines)


class Controller:
    """Mocked controller whose reported values can be changed between polls."""

    def __init__(self, aioclient_mock) -> None:
        self._mock = aioclient_mock
        self.values = load_fixture("syncvalues.txt")
        self.serve()

    def serve(self) -> None:
        """Register the read endpoints with the current values."""
        self._mock.clear_requests()
        self._mock.get(f"{BASE}/info.cgi", text=load_fixture("info.xml"))
        self._mock.get(f"{BASE}/config/hardware.xml", text=load_fixture("hardware.xml"))
        self._mock.get(f"{BASE}/syncvalues.cgi", text=self.values)
        serve_no_legacy(self._mock)

    def set(self, tid: str, value: str, vid: int = 0) -> None:
        """Change a value the controller reports from now on."""
        self.values = with_value(self.values, tid, value, vid)
        self.serve()

    def expect_write(self, query: str, response: str) -> None:
        """Answer one specific register change."""
        self._mock.get(f"{BASE}/setregister.cgi?{query}", text=response)

    @property
    def writes(self) -> list[str]:
        """Query strings of every register change requested so far."""
        urls = (str(call[1]) for call in self._mock.mock_calls)
        return [url.split("?", 1)[1] for url in urls if "setregister.cgi" in url]


@pytest.fixture
def controller(aioclient_mock) -> Controller:
    return Controller(aioclient_mock)


@pytest.fixture
def entry(hass) -> MockConfigEntry:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Boiler",
        unique_id=MAC,
        data={CONF_HOST: HOST, CONF_USERNAME: "root", CONF_PASSWORD: "example"},
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture
async def loaded(hass, controller, entry) -> MockConfigEntry:
    """A config entry set up against the mocked controller."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
