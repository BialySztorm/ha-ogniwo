"""Numeric settings of the Ogniwo integration."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .catalog import EntitySpec
from .coordinator import OgniwoConfigEntry, OgniwoCoordinator
from .entity import OgniwoEntity, to_number
from .models import RegisterDef

DEFAULT_STEP = 1.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OgniwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a number for every numeric setting the account may change."""
    coordinator = entry.runtime_data
    async_add_entities(
        OgniwoNumber(coordinator, spec) for spec in coordinator.specs_for(Platform.NUMBER)
    )


def format_value(value: float, step: float) -> str:
    """Snap a value to the register's step and format it with the step's decimals."""
    exact_step = Decimal(str(step))
    snapped = (Decimal(str(value)) / exact_step).to_integral_value(ROUND_HALF_UP) * exact_step
    decimals = max(0, -exact_step.normalize().as_tuple().exponent)
    return f"{snapped:.{decimals}f}"


def step_of(register: RegisterDef) -> float:
    """Return the step of a register, derived from its display precision when not given."""
    if register.step:
        return register.step
    if register.precision:
        return float(Decimal(1).scaleb(-register.precision))
    return DEFAULT_STEP


class OgniwoNumber(OgniwoEntity, NumberEntity):
    """A numeric register that can be changed within the range set by the controller."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: OgniwoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)
        register = spec.register
        self._step = step_of(register)
        self._attr_native_min_value = register.minimum
        self._attr_native_max_value = register.maximum
        self._attr_native_step = self._step
        self._attr_native_unit_of_measurement = self.unit
        if spec.curated is not None:
            self._attr_device_class = spec.curated.device_class

    @property
    def native_value(self) -> float | None:
        """Return the current setting."""
        return to_number(self.raw)

    async def async_set_native_value(self, value: float) -> None:
        """Write the setting to the controller."""
        await self.coordinator.async_write(
            self._vid, self._register.tid, format_value(value, self._step)
        )
