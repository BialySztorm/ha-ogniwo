"""Tests for parsing controller responses."""

import pytest

from custom_components.ogniwo.errors import OgniwoParseError, OgniwoWriteError
from custom_components.ogniwo.parser import (
    parse_dictionary,
    parse_info,
    parse_snapshot,
    parse_write_result,
)

from . import load_fixture, write_response


@pytest.fixture(scope="module")
def dictionary():
    return parse_dictionary(load_fixture("hardware.xml"))


@pytest.fixture(scope="module")
def snapshot():
    return parse_snapshot(load_fixture("syncvalues.txt"))


def test_info_exposes_controller_identity():
    info = parse_info(load_fixture("info.xml"))

    assert info.hardware_type == "pello_D"
    assert info.hardware_version == "4.0"
    assert info.software_version == "1.1.38.58"
    assert info.company == "ELEKTRO-SYSTEM"
    assert info.mac == "aabbccddeeff"
    assert info.name == "Testowy"


def test_info_rejects_response_without_hardware_node():
    with pytest.raises(OgniwoParseError):
        parse_info('<cmd status="ok"></cmd>')


def test_malformed_xml_raises_parse_error():
    with pytest.raises(OgniwoParseError):
        parse_dictionary("<hardware><vdevs>")


def test_dictionary_merges_device_types_sharing_the_controller_slot(dictionary):
    controller = dictionary.vdevs[0]

    assert controller.types == ("base", "pello_D")
    registers = dictionary.registers_for(0)
    assert "device_soft_version" in registers
    assert "tkot_value" in registers


def test_dictionary_reads_names_units_and_precision(dictionary):
    register = dictionary.registers_for(0)["tkot_value"]

    assert register.type == "float"
    assert register.name("pl") == "Temperatura kotła"
    assert register.name("en") == "Boiler temperature"
    assert register.name("de") == "Boiler temperature"
    assert register.unit == "°C"
    assert register.precision == 1
    assert register.groups["pl"] == "Czujniki temperatury"


def test_dictionary_reads_range_and_step_of_a_setpoint(dictionary):
    register = dictionary.registers_for(0)["kot_tzad"]

    assert (register.minimum, register.maximum, register.step) == (55, 80, 1)
    assert register.precision == 0


def test_dictionary_drops_ranges_that_are_not_real_ranges(dictionary):
    register = dictionary.registers_for(0)["dp_value"]

    assert register.minimum is None
    assert register.maximum is None


def test_dictionary_reads_enum_options_with_translations(dictionary):
    register = dictionary.registers_for(0)["pl_status"]

    assert [option.id for option in register.options] == ["0", "1", "2", "3", "4"]
    assert register.option("2").label("pl") == "GRZANIE"
    assert register.option("9") is None


def test_dictionary_falls_back_to_polish_unit_when_english_is_missing(dictionary):
    units = {register.unit for register in dictionary.registers_for(0).values()}

    assert None in units
    assert "" not in units


def test_dictionary_names_radio_slots(dictionary):
    sensor = dictionary.vdevs[85]

    assert sensor.types == ("bero.sensor",)
    assert sensor.name("pl") == "Temperatura w strefie 1"
    assert set(dictionary.registers_for(85)) >= {"temp", "rh", "bat", "sig", "alarm"}


def test_access_flag_depends_on_access_level(dictionary):
    register = dictionary.registers_for(0)["kot_tzad"]

    assert register.access(0) == "w"
    assert register.access(2) == "r"
    assert register.access(9) == "-"


def test_snapshot_reads_controller_values(snapshot):
    assert snapshot.value(0, "tkot_value") == "54.55"
    assert snapshot.value(0, "fuel_level") == "53"
    assert snapshot.controller_time == 1790944019


def test_snapshot_decodes_url_encoded_values(snapshot):
    assert snapshot.value(0, "localtimezone") == "CET-1CEST,M3.5.0/2,M10.5.0/3"
    assert snapshot.value(0, "pod_run_time_str") == "325m 24s"


def test_snapshot_treats_empty_value_as_missing(snapshot):
    assert snapshot.devices[0].values["tpod_value"] == ""
    assert snapshot.value(0, "tpod_value") is None
    assert snapshot.value(0, "no_such_register") is None
    assert snapshot.value(999, "temp") is None


def test_snapshot_reads_radio_sensor_with_its_own_timestamp(snapshot):
    sensor = snapshot.devices[85]

    assert sensor.timestamp == 1790943685
    assert sensor.values["temp"] == "23.16"
    assert sensor.values["t"] == "BT5BV3"


def test_snapshot_never_keeps_credentials(snapshot):
    for device in snapshot.devices.values():
        assert not [tid for tid in device.values if tid.startswith("auth_")]


def test_snapshot_skips_garbage_lines():
    snapshot = parse_snapshot("0;100;tkot_value:50.00;\rnot-a-line\r\r7;x;temp:1;\r")

    assert set(snapshot.devices) == {0}
    assert snapshot.value(0, "tkot_value") == "50.00"


def test_snapshot_without_controller_line_is_an_error():
    with pytest.raises(OgniwoParseError):
        parse_snapshot("85;100;temp:20.00;\r")


def test_write_result_accepts_ok_status():
    parse_write_result(
        '<cmd status="ok"><device id="0"><reg vid="0" tid="kot_tzad" status="ok"/></device></cmd>',
        "kot_tzad",
    )


def test_write_result_reports_refusal_reason():
    response = (
        '<cmd status="ok"><device id="0"><reg vid="0" tid="zzz" status="not_found"/></device></cmd>'
    )

    with pytest.raises(OgniwoWriteError, match="not_found"):
        parse_write_result(response, "zzz")


def test_write_result_without_matching_register_is_a_failure():
    with pytest.raises(OgniwoWriteError):
        parse_write_result('<cmd status="ok"><device id="0"></device></cmd>', "kot_tzad")


def test_info_without_a_valid_mac_is_rejected():
    without_mac = load_fixture("info.xml").replace('mac="aabbccddeeff"', 'mac=""')

    with pytest.raises(OgniwoParseError, match="MAC"):
        parse_info(without_mac)


def test_dictionary_drops_registers_whose_id_could_break_a_request():
    dictionary = parse_dictionary(
        '<hardware type="x" sv="1"><vdevs><vdev vid="0" type="base" idt="1"/></vdevs>'
        '<devices><device idt="1">'
        '<register tid="good_one" type="float"><config/></register>'
        '<register tid="bad&amp;out_pomp1" type="float"><config/></register>'
        "</device></devices></hardware>"
    )

    assert set(dictionary.registers_for(0)) == {"good_one"}


@pytest.mark.parametrize("bound", ["nan", "inf", "-inf", "abc"])
def test_dictionary_ignores_ranges_that_are_not_finite_numbers(bound):
    dictionary = parse_dictionary(
        '<hardware type="x" sv="1"><vdevs><vdev vid="0" type="base" idt="1"/></vdevs>'
        '<devices><device idt="1"><register tid="reg" type="float"><config>'
        f'<values min="0" max="{bound}" step="{bound}"/>'
        "</config></register></device></devices></hardware>"
    )
    register = dictionary.registers_for(0)["reg"]

    assert (register.minimum, register.maximum, register.step) == (None, None, None)


def test_snapshot_tolerates_a_byte_order_mark():
    snapshot = parse_snapshot("﻿0;100;tkot_value:50.00;\r")

    assert snapshot.value(0, "tkot_value") == "50.00"


def test_snapshot_drops_credentials_whatever_their_case():
    snapshot = parse_snapshot("0;100;AUTH_root:c2VjcmV0;Auth_user:c2VjcmV0;tkot_value:50.00;\r")

    assert set(snapshot.devices[0].values) == {"tkot_value"}


def test_snapshot_drops_values_with_malformed_register_ids():
    snapshot = parse_snapshot("0;100;a&b:1;ok_one:2;\r")

    assert set(snapshot.devices[0].values) == {"ok_one"}


@pytest.mark.parametrize("status", ["not a token", "x" * 500, ""])
def test_write_result_never_repeats_arbitrary_controller_text(status):
    with pytest.raises(OgniwoWriteError, match=r"not changed: unknown$"):
        parse_write_result(write_response("kot_tzad", status), "kot_tzad")


def test_write_result_reports_a_refused_request():
    with pytest.raises(OgniwoWriteError, match="refused"):
        parse_write_result('<cmd status="error"/>', "kot_tzad")
