"""Base entity of the Ogniwo integration."""

from __future__ import annotations

import math
import re

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .catalog import EntitySpec
from .coordinator import OgniwoCoordinator
from .models import RegisterDef

# The dictionary uses Polish abbreviations for some units.
UNITS = {"sek": "s", "sec": "s", "godz": "h", "hr": "h"}

# float() would also accept "nan", "inf", "1e999" and digit separators.
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


class OgniwoEntity(CoordinatorEntity[OgniwoCoordinator]):
    """An entity backed by one register of one device slot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OgniwoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._vid = spec.vid
        self._register: RegisterDef = spec.register
        self._language = coordinator.language
        self._attr_unique_id = coordinator.unique_id(spec.vid, spec.register.tid)
        self._attr_device_info = coordinator.device_info(spec.vid)
        self._attr_entity_registry_enabled_default = spec.enabled
        self._attr_entity_category = spec.category
        if spec.curated is not None:
            self._attr_translation_key = spec.curated.key
        else:
            self._attr_name = spec.register.name(self._language)

    @property
    def suggested_object_id(self) -> str | None:
        """Keep entity ids in English regardless of the language of entity names."""
        return self._spec.key

    @property
    def available(self) -> bool:
        """Radio nodes keep their last value on the controller after they go silent."""
        return super().available and not self.coordinator.is_stale(self._vid)

    @property
    def raw(self) -> str | None:
        """Raw register value; None when the controller reports nothing."""
        return self.coordinator.data.value(self._vid, self._register.tid)

    @property
    def unit(self) -> str | None:
        """Unit of the register in Home Assistant notation."""
        if self._spec.curated is not None and self._spec.curated.unit:
            return self._spec.curated.unit
        unit = self._register.unit
        return UNITS.get(unit, unit) if unit else None

    def option_states(self) -> dict[str, str]:
        """Map raw option ids to states: stable keys when curated, else controller labels."""
        if self._spec.curated is not None and self._spec.curated.options:
            return dict(self._spec.curated.options)
        states: dict[str, str] = {}
        for option in self._register.options:
            label = option.label(self._language)
            # Some registers reuse one label for several values.
            states[option.id] = f"{label} ({option.id})" if label in states.values() else label
        return states


def to_number(raw: str | None) -> float | int | None:
    """Convert a raw register value to a number."""
    if raw is None or not _NUMBER.match(raw):
        return None
    value = float(raw)
    if not math.isfinite(value):
        return None
    return int(value) if value.is_integer() else value
