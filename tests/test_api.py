"""Tests for the HTTP client."""

import gzip

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.ogniwo.api import OgniwoClient
from custom_components.ogniwo.errors import (
    OgniwoAuthError,
    OgniwoConnectionError,
    OgniwoInvalidHostError,
    OgniwoParseError,
    OgniwoWriteError,
)

from . import load_fixture, write_response

HOST = "192.0.2.10"
BASE = f"http://{HOST}"


@pytest.fixture
async def client(hass, aioclient_mock):
    return OgniwoClient(async_get_clientsession(hass), HOST, "root", "example")


async def test_reads_info(client, aioclient_mock):
    aioclient_mock.get(f"{BASE}/info.cgi", text=load_fixture("info.xml"))

    info = await client.async_get_info()

    assert info.name == "Testowy"
    assert client.base_url == BASE


async def test_reads_dictionary_and_snapshot(client, aioclient_mock):
    aioclient_mock.get(f"{BASE}/config/hardware.xml", text=load_fixture("hardware.xml"))
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", text=load_fixture("syncvalues.txt"))

    dictionary = await client.async_get_dictionary()
    snapshot = await client.async_get_snapshot()

    assert "tkot_value" in dictionary.registers_for(0)
    assert snapshot.value(0, "tkot_value") == "54.55"


async def test_gzipped_dictionary_is_unpacked_without_the_encoding_header(
    client, aioclient_mock
):
    """Firmware serves the dictionary gzipped and does not always say so."""
    packed = gzip.compress(load_fixture("hardware.xml").encode())
    aioclient_mock.get(f"{BASE}/config/hardware.xml", content=packed)

    dictionary = await client.async_get_dictionary()

    assert "tkot_value" in dictionary.registers_for(0)


async def test_damaged_gzip_response_is_a_parse_error(client, aioclient_mock):
    aioclient_mock.get(f"{BASE}/config/hardware.xml", content=b"\x1f\x8b\x08truncated")

    with pytest.raises(OgniwoParseError):
        await client.async_get_dictionary()


async def test_unauthorized_response_is_an_auth_error(client, aioclient_mock):
    aioclient_mock.get(f"{BASE}/info.cgi", status=401)

    with pytest.raises(OgniwoAuthError):
        await client.async_get_info()


async def test_http_error_is_a_connection_error(client, aioclient_mock):
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", status=500)

    with pytest.raises(OgniwoConnectionError):
        await client.async_get_snapshot()


@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError("down"), TimeoutError()])
async def test_network_failure_is_a_connection_error(client, aioclient_mock, error):
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", exc=error)

    with pytest.raises(OgniwoConnectionError):
        await client.async_get_snapshot()


async def test_write_sends_device_and_register_in_order(client, aioclient_mock):
    aioclient_mock.get(
        f"{BASE}/setregister.cgi?device=0&kot_tzad=65",
        text=write_response("kot_tzad"),
    )

    await client.async_set_register(0, "kot_tzad", "65")

    assert str(aioclient_mock.mock_calls[0][1]) == f"{BASE}/setregister.cgi?device=0&kot_tzad=65"


async def test_refused_write_raises(client, aioclient_mock):
    aioclient_mock.get(
        f"{BASE}/setregister.cgi?device=0&zzz=1",
        text=write_response("zzz", "not_found"),
    )

    with pytest.raises(OgniwoWriteError):
        await client.async_set_register(0, "zzz", "1")


@pytest.mark.parametrize(
    ("tid", "value"),
    [
        ("kot_tzad", "1&out_pomp1=1"),
        ("kot_tzad", "nan"),
        ("kot_tzad", ""),
        ("kot_tzad&out_pomp1", "1"),
        ("a=b", "1"),
    ],
)
async def test_write_refuses_anything_that_could_reach_another_register(
    client, aioclient_mock, tid, value
):
    with pytest.raises(OgniwoWriteError):
        await client.async_set_register(0, tid, value)

    assert aioclient_mock.call_count == 0


async def test_forbidden_response_is_an_auth_error(client, aioclient_mock):
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", status=403)

    with pytest.raises(OgniwoAuthError):
        await client.async_get_snapshot()


async def test_redirect_is_not_followed(client, aioclient_mock):
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", status=302, headers={"Location": "http://x/"})

    with pytest.raises(OgniwoConnectionError):
        await client.async_get_snapshot()


async def test_oversized_response_is_rejected(client, aioclient_mock):
    aioclient_mock.get(f"{BASE}/syncvalues.cgi", text="0;1;a:1;\r" * 600_000)

    with pytest.raises(OgniwoParseError):
        await client.async_get_snapshot()


@pytest.mark.parametrize("host", ["http://192.0.2.10", "192.0.2.10:8080", "user:secret@192.0.2.10"])
async def test_invalid_host_is_reported_without_repeating_it(hass, aioclient_mock, host):
    with pytest.raises(OgniwoInvalidHostError) as error:
        OgniwoClient(async_get_clientsession(hass), host, "root", "example")

    assert "secret" not in str(error.value)
