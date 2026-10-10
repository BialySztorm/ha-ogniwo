"""Tests for converting raw register values."""

import pytest

from custom_components.ogniwo.entity import to_number
from custom_components.ogniwo.models import localized
from custom_components.ogniwo.sensor import to_datetime


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("65", 65), ("54.55", 54.55), ("-3.5", -3.5), ("54.00", 54), ("0", 0)],
)
def test_numbers_are_converted(raw, expected):
    assert to_number(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "nan", "inf", "-inf", "1e999", "1_0", "abc", "1.", " 1"])
def test_anything_but_a_plain_decimal_is_not_a_number(raw):
    assert to_number(raw) is None


def test_unix_time_is_converted_to_utc():
    assert to_datetime("1790944010").isoformat() == "2026-10-02T12:26:50+00:00"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1790944010", "2026-10-02T12:00:00+00:00"),
        ("1790945999", "2026-10-02T13:00:00+00:00"),
    ],
)
def test_unix_time_can_be_rounded_to_the_hour(raw, expected):
    assert to_datetime(raw, 3600).isoformat() == expected


@pytest.mark.parametrize("raw", ["0", "nan", "99999999999999999999", "abc"])
def test_impossible_unix_time_is_unknown(raw):
    assert to_datetime(raw) is None


@pytest.mark.parametrize(
    ("language", "expected"),
    [("pl", "kocioł"), ("pl-PL", "kocioł"), ("en-GB", "boiler"), ("de", "boiler")],
)
def test_label_language_falls_back_to_base_language_then_english(language, expected):
    assert localized({"en": "boiler", "pl": "kocioł"}, language) == expected


def test_label_falls_back_to_any_language_when_english_is_missing():
    assert localized({"cs": "kotel"}, "de") == "kotel"
    assert localized({}, "de") is None
