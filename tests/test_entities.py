"""Tests for the entities created from controller registers."""

import pytest
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from . import write_response
from .conftest import BASE


async def refresh(hass, entry):
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def registry_entry(hass, entity_id):
    return er.async_get(hass).async_get(entity_id)


# Sensors


async def test_temperature_sensor(hass, loaded):
    state = hass.states.get("sensor.boiler_water_temperature")

    assert state.state == "54.55"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["state_class"] == "measurement"
    assert state.name == "Boiler Water temperature"


async def test_empty_value_of_enabled_sensor_is_unknown(hass, controller, loaded):
    controller.set("ob1_pok_tact", "")

    await refresh(hass, loaded)

    assert hass.states.get("sensor.boiler_room_temperature").state == "unknown"


async def test_curated_enum_sensor_uses_stable_states(hass, controller, loaded):
    state = hass.states.get("sensor.boiler_burner_status")
    assert state.state == "stop"
    assert state.attributes["options"] == [
        "stop",
        "ignition",
        "heating",
        "extinguishing",
        "cleaning",
    ]

    controller.set("pl_status", "2")
    await refresh(hass, loaded)

    assert hass.states.get("sensor.boiler_burner_status").state == "heating"


async def test_burner_power_stage_is_an_enum_not_a_percentage(hass, controller, loaded):
    state = hass.states.get("sensor.boiler_burner_power_stage")
    assert state.state == "off"
    assert state.attributes["options"] == ["off", "minimum", "intermediate", "maximum"]
    assert "unit_of_measurement" not in state.attributes
    assert "state_class" not in state.attributes

    controller.set("pl_power", "3")
    await refresh(hass, loaded)

    assert hass.states.get("sensor.boiler_burner_power_stage").state == "maximum"


async def test_enum_value_missing_from_the_dictionary_is_unknown(hass, controller, loaded):
    controller.set("pl_status_ext", "999")

    await refresh(hass, loaded)

    assert hass.states.get("sensor.boiler_burner_status_detail").state == "unknown"


async def test_timestamp_sensor(hass, loaded):
    state = hass.states.get("sensor.boiler_next_refuel")

    assert state.attributes["device_class"] == "timestamp"
    assert state.state == "2026-10-14T00:00:00+00:00"


async def test_estimate_recalculated_on_every_poll_does_not_change_state(hass, controller, loaded):
    before = hass.states.get("sensor.boiler_next_refuel")

    controller.set("next_fuel_time", "1791936670")
    await refresh(hass, loaded)

    assert hass.states.get("sensor.boiler_next_refuel").last_changed == before.last_changed


async def test_duration_sensor_keeps_native_seconds(hass, loaded):
    state = hass.states.get("sensor.boiler_burner_runtime")

    assert state.attributes["device_class"] == "duration"
    assert state.attributes["state_class"] == "total_increasing"


async def test_undocumented_register_is_exposed(hass, loaded):
    state = hass.states.get("sensor.boiler_pellets_since_cleaning")

    assert state.state == "251.96"
    assert state.attributes["unit_of_measurement"] == "kg"


async def test_charted_register_is_presented_as_a_temperature(hass, loaded):
    state = hass.states.get("sensor.boiler_tzew_act")

    assert state.state == "22.54"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["state_class"] == "measurement"


async def test_uncurated_sensor_is_disabled_and_named_by_the_controller(hass, loaded):
    entity = registry_entry(hass, "sensor.boiler_pl_hfire")

    assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entity.original_name == "Ilość rozpaleń w ciągu ostatniej godziny"
    assert hass.states.get("sensor.boiler_pl_hfire") is None


async def test_uncurated_entity_names_follow_the_configured_language(hass, controller, entry):
    hass.config.language = "pl"
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity = registry_entry(hass, "sensor.boiler_kot_hist")

    assert entity.original_name == "Histereza załączenia kotła"


async def test_radio_sensor_values(hass, loaded):
    assert hass.states.get("sensor.boiler_zone_1_temperature_temperature").state == "23.16"
    assert hass.states.get("sensor.boiler_zone_1_temperature_humidity").state == "51.63"
    assert hass.states.get("sensor.boiler_zone_1_temperature_battery").state == "100"


async def test_silent_radio_sensor_becomes_unavailable(hass, controller, loaded):
    controller.values = controller.values.replace("\r85;1790943685;", "\r85;1790900000;")
    controller.serve()

    await refresh(hass, loaded)

    assert hass.states.get("sensor.boiler_zone_1_temperature_temperature").state == "unavailable"
    assert hass.states.get("sensor.boiler_water_temperature").state == "54.55"


# Binary sensors


async def test_output_binary_sensor(hass, controller, loaded):
    assert hass.states.get("binary_sensor.boiler_pump_1").state == "off"

    controller.set("out_pomp1", "1")
    await refresh(hass, loaded)

    state = hass.states.get("binary_sensor.boiler_pump_1")
    assert state.state == "on"
    assert state.attributes["device_class"] == "running"


async def test_output_with_several_active_values_is_on(hass, controller, loaded):
    controller.set("mpl_clean", "2")

    await refresh(hass, loaded)

    assert hass.states.get("binary_sensor.boiler_burner_cleaning").state == "on"


async def test_alarm_decodes_active_conditions(hass, controller, loaded):
    alarm = "binary_sensor.boiler_alarm_rozp"
    assert hass.states.get(alarm).state == "off"
    assert hass.states.get(alarm).attributes["messages"] == []

    controller.set("alarm_rozp", "3")
    await refresh(hass, loaded)

    state = hass.states.get(alarm)
    assert state.state == "on"
    assert state.attributes["device_class"] == "problem"
    assert len(state.attributes["messages"]) == 2


async def test_alarm_summary_lists_active_alarms(hass, controller, loaded):
    assert hass.states.get("binary_sensor.boiler_alarm").state == "off"

    controller.set("alarm_stb", "1")
    controller.set("alarm", "2", vid=85)
    await refresh(hass, loaded)

    state = hass.states.get("binary_sensor.boiler_alarm")
    assert state.state == "on"
    assert len(state.attributes["active"]) == 2
    assert any("Safety temperature limiter" in entry for entry in state.attributes["active"])


# Numbers


async def test_setpoint_number_reflects_controller_range(hass, loaded):
    state = hass.states.get("number.boiler_setpoint")

    assert state.state == "65"
    assert (state.attributes["min"], state.attributes["max"], state.attributes["step"]) == (
        55,
        80,
        1,
    )
    assert state.attributes["unit_of_measurement"] == "°C"


async def test_changing_a_setpoint_writes_one_register(hass, controller, loaded):
    controller.expect_write("device=0&kot_tzad=70", write_response("kot_tzad"))

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.boiler_setpoint", "value": 70},
        blocking=True,
    )

    assert controller.writes == ["device=0&kot_tzad=70"]


async def test_state_follows_consecutive_writes_immediately(hass, controller, loaded):
    for value in ("60", "65"):
        controller.set("kot_tzad", value)
        controller.expect_write(f"device=0&kot_tzad={value}", write_response("kot_tzad"))

        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.boiler_setpoint", "value": int(value)},
            blocking=True,
        )

        assert hass.states.get("number.boiler_setpoint").state == value


async def test_fractional_setting_keeps_one_decimal(hass, controller, loaded):
    controller.expect_write("device=0&ob1_pok_norm=22.5", write_response("ob1_pok_norm"))

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.boiler_room_temperature_normal", "value": 22.5},
        blocking=True,
    )

    assert controller.writes == ["device=0&ob1_pok_norm=22.5"]


async def test_value_outside_the_controller_range_is_rejected_locally(hass, controller, loaded):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.boiler_setpoint", "value": 95},
            blocking=True,
        )

    assert controller.writes == []


async def test_refused_write_is_reported(hass, controller, loaded):
    controller.expect_write("device=0&kot_tzad=70", write_response("kot_tzad", "access_denied"))

    with pytest.raises(HomeAssistantError, match="access_denied"):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.boiler_setpoint", "value": 70},
            blocking=True,
        )


async def test_step_is_derived_from_precision_when_the_dictionary_gives_none(hass, loaded):
    state = hass.states.get("number.boiler_room_temperature_normal")

    assert state.attributes["step"] == 0.1


async def test_rejected_credentials_on_write_start_reauth(hass, aioclient_mock, loaded):
    aioclient_mock.get(f"{BASE}/setregister.cgi?device=0&kot_tzad=70", status=401)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.boiler_setpoint", "value": 70},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert list(loaded.async_get_active_flows(hass, {SOURCE_REAUTH}))


# Selects


async def test_select_shows_current_option(hass, loaded):
    state = hass.states.get("select.boiler_season_mode")

    assert state.state == "auto_summer"
    assert state.attributes["options"] == ["winter", "summer", "auto_summer"]


async def test_selecting_an_option_writes_its_raw_id(hass, controller, loaded):
    controller.expect_write("device=0&zima_lato=0", write_response("zima_lato"))

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.boiler_season_mode", "option": "winter"},
        blocking=True,
    )

    assert controller.writes == ["device=0&zima_lato=0"]


# Buttons


async def test_acknowledge_alarms_button(hass, controller, loaded):
    controller.expect_write("device=0&cmd_ackalarm=1", write_response("cmd_ackalarm"))

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.boiler_acknowledge_alarms"},
        blocking=True,
    )

    assert controller.writes == ["device=0&cmd_ackalarm=1"]


async def test_restart_button_is_disabled_by_default(hass, loaded):
    entity = registry_entry(hass, "button.boiler_restart")

    assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_controls_are_limited_to_the_reviewed_set(hass, loaded):
    registry = er.async_get(hass)
    controls = [
        entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, loaded.entry_id)
        if entity.domain in ("number", "select", "button", "switch")
    ]

    assert sorted(controls) == [
        "button.boiler_acknowledge_alarms",
        "button.boiler_restart",
        "number.boiler_buffer_setpoint",
        "number.boiler_dhw_setpoint",
        "number.boiler_mixing_valve_setpoint",
        "number.boiler_room_temperature_comfort",
        "number.boiler_room_temperature_low",
        "number.boiler_room_temperature_normal",
        "number.boiler_setpoint",
        "select.boiler_dhw_mode",
        "select.boiler_season_mode",
    ]


async def test_room_heating_demand_follows_the_undocumented_room_regulator_register(
    hass, controller, loaded
):
    assert hass.states.get("binary_sensor.boiler_room_heating_demand").state == "off"

    controller.set("ob1_pok_heat", "1")
    await refresh(hass, loaded)

    assert hass.states.get("binary_sensor.boiler_room_heating_demand").state == "on"
