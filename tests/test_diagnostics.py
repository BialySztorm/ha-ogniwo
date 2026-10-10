"""Tests for diagnostics."""

from custom_components.ogniwo.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_hide_credentials_and_identity(hass, loaded):
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded)

    assert diagnostics["config"] == {
        "host": "**REDACTED**",
        "username": "**REDACTED**",
        "password": "**REDACTED**",
    }
    controller = diagnostics["values"]["0"]["values"]
    assert controller["tkot_value"] == "54.55"
    assert controller["device_sn"] == "**REDACTED**"
    assert controller["eth_mac"] == "**REDACTED**"
    assert controller["localtimezone"] == "**REDACTED**"
    assert not [tid for tid in controller if tid.startswith("auth_")]
    assert not [tid for tid in controller if tid.endswith("_prog")]
    assert "tbl" not in diagnostics["values"]["100"]["values"]
    assert diagnostics["controller"]["access_level"] == 0
    assert diagnostics["entities"] > 100
