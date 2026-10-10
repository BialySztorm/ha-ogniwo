"""Tests for formatting values written to the controller."""

import pytest

from custom_components.ogniwo.models import RegisterDef
from custom_components.ogniwo.number import format_value, step_of


@pytest.mark.parametrize(
    ("value", "step", "expected"),
    [
        (70.0, 1.0, "70"),
        (22.5, 0.1, "22.5"),
        (22.0, 0.1, "22.0"),
        (0.3, 0.1, "0.3"),
        (-5.0, 1.0, "-5"),
        (12.25, 0.05, "12.25"),
    ],
)
def test_value_has_as_many_decimals_as_the_step(value, step, expected):
    assert format_value(value, step) == expected


@pytest.mark.parametrize(
    ("value", "step", "expected"),
    [(23.0, 5.0, "25"), (22.0, 5.0, "20"), (22.46, 0.1, "22.5"), (64.6, 1.0, "65")],
)
def test_value_is_snapped_to_the_step(value, step, expected):
    assert format_value(value, step) == expected


@pytest.mark.parametrize(
    ("step", "precision", "expected"),
    [(0.5, 1, 0.5), (None, 1, 0.1), (None, 2, 0.01), (None, 0, 1.0), (None, None, 1.0)],
)
def test_step_falls_back_to_the_display_precision(step, precision, expected):
    register = RegisterDef(tid="reg", type="float", step=step, precision=precision)

    assert step_of(register) == expected
