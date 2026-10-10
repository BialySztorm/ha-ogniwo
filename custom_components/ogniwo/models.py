"""Data model of a Ogniwo controller: register dictionary and value snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .const import MAIN_VID

FALLBACK_LANGUAGE = "en"

ACCESS_READ = "r"
ACCESS_WRITE = "w"
ACCESS_EXECUTE = "x"
ACCESS_NONE = "-"


def localized(labels: Mapping[str, str], language: str) -> str | None:
    """Pick the label for a language, falling back to English and then to anything."""
    # Home Assistant may be set to a regional variant such as en-GB.
    for candidate in (language, language.split("-", maxsplit=1)[0], FALLBACK_LANGUAGE):
        if label := labels.get(candidate):
            return label
    return next((label for label in labels.values() if label), None)


@dataclass(frozen=True, slots=True)
class RegisterOption:
    """One allowed value of an enum register, or one bit of an alarm register."""

    id: str
    labels: Mapping[str, str]

    def label(self, language: str) -> str:
        """Return the option label, falling back to its raw id."""
        return localized(self.labels, language) or self.id


@dataclass(frozen=True, slots=True)
class RegisterDef:
    """Definition of a register as published by the controller."""

    tid: str
    type: str
    priv: str = ""
    api: str = ""
    names: Mapping[str, str] = field(default_factory=dict)
    groups: Mapping[str, str] = field(default_factory=dict)
    unit: str | None = None
    precision: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: tuple[RegisterOption, ...] = ()

    def access(self, level: int) -> str:
        """Return the access flag (r, w, x or -) for an access level."""
        if 0 <= level < len(self.priv):
            return self.priv[level]
        return ACCESS_NONE

    def name(self, language: str) -> str:
        """Return the register name, falling back to its id."""
        return localized(self.names, language) or self.tid

    def option(self, option_id: str) -> RegisterOption | None:
        """Find an option by its raw id."""
        return next((opt for opt in self.options if opt.id == option_id), None)


@dataclass(frozen=True, slots=True)
class VirtualDevice:
    """A device slot of the controller: the controller itself, a radio node or a room."""

    vid: int
    types: tuple[str, ...]
    idts: tuple[str, ...]
    names: Mapping[str, str] = field(default_factory=dict)

    def name(self, language: str) -> str | None:
        """Return the slot name in the given language."""
        return localized(self.names, language)


@dataclass(frozen=True, slots=True)
class Dictionary:
    """Register dictionary: device slots and the registers of each device type."""

    hardware_type: str
    version: str
    vdevs: Mapping[int, VirtualDevice]
    registers: Mapping[str, Mapping[str, RegisterDef]]

    def registers_for(self, vid: int) -> dict[str, RegisterDef]:
        """Return the registers of a device slot, merged over all its device types."""
        vdev = self.vdevs.get(vid)
        if vdev is None:
            return {}
        merged: dict[str, RegisterDef] = {}
        for idt in vdev.idts:
            merged.update(self.registers.get(idt, {}))
        return merged


@dataclass(frozen=True, slots=True)
class DeviceValues:
    """Raw register values of one device slot."""

    vid: int
    timestamp: int
    values: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Values of all device slots read in one request."""

    devices: Mapping[int, DeviceValues]

    def value(self, vid: int, tid: str) -> str | None:
        """Return a raw value, or None when missing or empty (sensor not connected)."""
        device = self.devices.get(vid)
        if device is None:
            return None
        return device.values.get(tid) or None

    @property
    def controller_time(self) -> int:
        """Unix time of the controller at the moment of the read."""
        main = self.devices.get(MAIN_VID)
        return main.timestamp if main else 0


@dataclass(frozen=True, slots=True)
class ControllerInfo:
    """Identity of the controller."""

    hardware_type: str
    hardware_version: str
    software_version: str
    company: str
    mac: str
    name: str
