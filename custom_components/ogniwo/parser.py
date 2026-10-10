"""Parsers for the responses of a Ogniwo controller."""

from __future__ import annotations

import math
import re
from urllib.parse import unquote
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from .const import MAIN_VID
from .errors import OgniwoParseError, OgniwoWriteError
from .models import (
    ControllerInfo,
    DeviceValues,
    Dictionary,
    RegisterDef,
    RegisterOption,
    Snapshot,
    VirtualDevice,
)

# syncvalues.cgi returns the credentials of every access level among the registers.
SECRET_PREFIXES = ("auth_",)

STATUS_OK = "ok"
STATUS_UNKNOWN = "unknown"

# The register holding the same MAC that info.cgi reports.
REGISTER_MAC = "eth_mac"

_DECIMAL_FORMAT = re.compile(r"^0(?:\.(0+))?$")
# Register ids end up in request URLs and entity ids.
_REGISTER_ID = re.compile(r"^[A-Za-z0-9_]+$")
_MAC = re.compile(r"^[0-9a-f]{12}$")
_STATUS = re.compile(r"^[A-Za-z0-9_]{1,40}$")
_BOM = "\ufeff"


def _parse_xml(text: str) -> Element:
    try:
        return fromstring(text)
    except (ParseError, DefusedXmlException) as err:
        raise OgniwoParseError(f"Invalid XML: {err}") from err


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _labels(node: Element | None) -> dict[str, str]:
    if node is None:
        return {}
    return {language: label for language, label in node.attrib.items() if label}


def parse_info(text: str) -> ControllerInfo:
    """Parse info.cgi."""
    hardware = _parse_xml(text).find("hardware")
    if hardware is None:
        raise OgniwoParseError("info.cgi response has no hardware node")
    mac = hardware.get("mac", "").lower()
    if not _MAC.match(mac):
        # The MAC identifies the controller; without it two controllers would collide.
        raise OgniwoParseError("info.cgi response has no valid MAC address")
    return ControllerInfo(
        hardware_type=hardware.get("type", ""),
        hardware_version=hardware.get("hardwareversion", ""),
        software_version=hardware.get("softwareversion", ""),
        company=hardware.get("company", ""),
        mac=mac,
        name=hardware.get("device_name", ""),
    )


def parse_identity(snapshot: Snapshot) -> ControllerInfo | None:
    """Build the identity of the controller out of its own registers.

    info.cgi is the usual source, but firmware refuses it to panel accounts
    below root. Every fact it carries except the manufacturer sits in registers
    those accounts do read, and the MAC is the same one, so an entry identifies
    the same controller whichever account configured it. None means the
    registers do not identify it either.
    """
    mac = (snapshot.value(MAIN_VID, REGISTER_MAC) or "").lower()
    if not _MAC.match(mac):
        return None
    return ControllerInfo(
        hardware_type=snapshot.value(MAIN_VID, "device_type") or "",
        hardware_version=snapshot.value(MAIN_VID, "device_hard_version") or "",
        software_version=snapshot.value(MAIN_VID, "device_soft_version") or "",
        company="",
        mac=mac,
        name=snapshot.value(MAIN_VID, "device_name") or "",
    )


def _parse_precision(config: Element) -> int | None:
    fmt = config.find("format")
    if fmt is None:
        return None
    match = _DECIMAL_FORMAT.match(fmt.get("en") or fmt.get("pl") or "")
    if match is None:
        return None
    return len(match.group(1) or "")


def _parse_unit(config: Element) -> str | None:
    unit = config.find("unit")
    if unit is None:
        return None
    return unit.get("en") or unit.get("pl") or None


def _parse_register(node: Element) -> RegisterDef:
    config = node.find("config")
    if config is None:
        return RegisterDef(tid=node.get("tid", ""), type=node.get("type", ""))

    values = config.find("values")
    minimum = maximum = step = None
    options: tuple[RegisterOption, ...] = ()
    if values is not None:
        minimum = _to_float(values.get("min"))
        maximum = _to_float(values.get("max"))
        step = _to_float(values.get("step"))
        # Read-only registers often carry placeholder ranges such as 0..0 or 0..-1.
        if minimum is None or maximum is None or maximum <= minimum:
            minimum = maximum = None
        options = tuple(
            RegisterOption(
                id=val.get("id", ""),
                labels={k: v for k, v in val.attrib.items() if k != "id" and v},
            )
            for val in values.findall("val")
        )

    return RegisterDef(
        tid=node.get("tid", ""),
        type=node.get("type", ""),
        priv=node.get("priv", ""),
        api=node.get("api", ""),
        names=_labels(config.find("name")),
        groups=_labels(config.find("group")),
        unit=_parse_unit(config),
        precision=_parse_precision(config),
        minimum=minimum,
        maximum=maximum,
        step=step,
        options=options,
    )


def _parse_vdevs(root: Element) -> dict[int, VirtualDevice]:
    vdevs: dict[int, VirtualDevice] = {}
    for node in root.findall("vdevs/vdev"):
        try:
            vid = int(node.get("vid", ""))
        except ValueError:
            continue
        names = _labels(node.find("config/name"))
        known = vdevs.get(vid)
        vdevs[vid] = VirtualDevice(
            vid=vid,
            types=(*(known.types if known else ()), node.get("type", "")),
            idts=(*(known.idts if known else ()), node.get("idt", "")),
            names={**(known.names if known else {}), **names},
        )
    return vdevs


def parse_dictionary(text: str) -> Dictionary:
    """Parse config/hardware.xml, the register dictionary of the controller."""
    root = _parse_xml(text)
    registers: dict[str, dict[str, RegisterDef]] = {}
    for device in root.findall("devices/device"):
        parsed = (_parse_register(node) for node in device.findall("register"))
        registers[device.get("idt", "")] = {
            reg.tid: reg for reg in parsed if _REGISTER_ID.match(reg.tid)
        }

    return Dictionary(
        hardware_type=root.get("type", ""),
        version=root.get("sv", ""),
        vdevs=_parse_vdevs(root),
        registers=registers,
    )


def _parse_line(line: str) -> DeviceValues | None:
    parts = line.split(";")
    if len(parts) < 2:
        return None
    try:
        vid, timestamp = int(parts[0]), int(parts[1])
    except ValueError:
        return None

    values: dict[str, str] = {}
    for part in parts[2:]:
        tid, separator, raw = part.partition(":")
        if not separator or not _REGISTER_ID.match(tid):
            continue
        if tid.casefold().startswith(SECRET_PREFIXES):
            continue
        values[tid] = unquote(raw)
    return DeviceValues(vid=vid, timestamp=timestamp, values=values)


def parse_snapshot(text: str) -> Snapshot:
    """Parse syncvalues.cgi: one line of `vid;unixtime;tid:value;...` per device slot."""
    devices = {
        device.vid: device
        for line in text.lstrip(_BOM).splitlines()
        if (device := _parse_line(line.strip())) is not None
    }
    if MAIN_VID not in devices:
        raise OgniwoParseError("syncvalues.cgi response has no controller line")
    return Snapshot(devices=devices)


def _status(node: Element) -> str:
    """Return a status reported by the controller, reduced to a safe token."""
    status = node.get("status") or ""
    return status if _STATUS.match(status) else STATUS_UNKNOWN


def parse_write_result(text: str, tid: str) -> None:
    """Check the response of setregister.cgi for the given register."""
    root = _parse_xml(text)
    if _status(root) != STATUS_OK:
        raise OgniwoWriteError(f"Controller refused the request: {_status(root)}")
    for reg in root.iter("reg"):
        if reg.get("tid") != tid:
            continue
        if _status(reg) != STATUS_OK:
            raise OgniwoWriteError(f"Register {tid} was not changed: {_status(reg)}")
        return
    raise OgniwoWriteError(f"Controller did not confirm the change of register {tid}")
