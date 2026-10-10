"""Rules turning controller registers into entities.

A small curated set of registers gets stable English keys, device classes and
translations; only curated settings can be changed. Every other register found
in the dictionary becomes a read-only entity named by the controller itself.

Controllers of this family differ in which registers they expose, and a curated
set cannot cover a register map nobody has seen yet. Uncurated registers that
the controller plots in its own web panel (`api="|chart|"`) are therefore
enabled too: the controller itself says they are worth watching. The remaining
ones are created disabled, to be switched on by hand when needed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, Platform, UnitOfTime

from .const import MAIN_VID
from .models import (
    ACCESS_EXECUTE,
    ACCESS_WRITE,
    Dictionary,
    RegisterDef,
    RegisterOption,
    Snapshot,
    VirtualDevice,
)

TYPE_ALARM = "alarm"
TYPE_COMMAND = "cmd"
TYPE_ENUM = "enum"
TYPE_TIMESTAMP = "unixtime"
NUMERIC_TYPES = frozenset({"float", "int", "interval"})

ROOM_DEVICE_TYPE = "bero.room"

# The dictionary tags registers the web panel charts; those are the measured
# values, as opposed to the hundreds of configuration parameters next to them.
API_CHART = "chart"

# Only curated entries of these platforms can change the controller. Every other
# register is read-only here, whatever access the controller itself would grant.
CONTROL_PLATFORMS = frozenset({Platform.NUMBER, Platform.SELECT, Platform.BUTTON})

SECONDS_PER_HOUR = 3600

MEASUREMENT = SensorStateClass.MEASUREMENT
TOTAL_INCREASING = SensorStateClass.TOTAL_INCREASING
TEMPERATURE = SensorDeviceClass.TEMPERATURE
DURATION = SensorDeviceClass.DURATION
RUNNING = BinarySensorDeviceClass.RUNNING


@dataclass(frozen=True, slots=True, kw_only=True)
class Curated:
    """Hand-written presentation of a register."""

    key: str
    platform: Platform
    device_class: str | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None
    suggested_unit: str | None = None
    # Raw option id -> stable state, so automations do not depend on the UI language.
    options: Mapping[str, str] | None = None
    # Timestamps are rounded to this many seconds.
    resolution: int | None = None
    enabled: bool = True
    category: EntityCategory | None = None


@dataclass(frozen=True, slots=True)
class EntitySpec:
    """An entity to create for a register of a device slot."""

    vid: int
    register: RegisterDef
    platform: Platform
    curated: Curated | None
    enabled: bool
    category: EntityCategory | None

    @property
    def key(self) -> str:
        """Stable key used for the entity id and translations."""
        return self.curated.key if self.curated else self.register.tid


def _temperature(key: str, **kwargs) -> Curated:
    return Curated(
        key=key,
        platform=Platform.SENSOR,
        device_class=TEMPERATURE,
        state_class=MEASUREMENT,
        **kwargs,
    )


def _measurement(key: str, **kwargs) -> Curated:
    return Curated(key=key, platform=Platform.SENSOR, state_class=MEASUREMENT, **kwargs)


def _enum(key: str, options: Mapping[str, str], **kwargs) -> Curated:
    return Curated(
        key=key,
        platform=Platform.SENSOR,
        device_class=SensorDeviceClass.ENUM,
        options=options,
        **kwargs,
    )


def _output(key: str) -> Curated:
    return Curated(key=key, platform=Platform.BINARY_SENSOR, device_class=RUNNING)


def _input(key: str, **kwargs) -> Curated:
    return Curated(key=key, platform=Platform.BINARY_SENSOR, **kwargs)


def _setpoint(key: str) -> Curated:
    return Curated(key=key, platform=Platform.NUMBER, device_class=NumberDeviceClass.TEMPERATURE)


BURNER_STATUS = {
    "0": "stop",
    "1": "ignition",
    "2": "heating",
    "3": "extinguishing",
    "4": "cleaning",
}

# Power stage of the burner in the heating phase, as named in the controller manual.
BURNER_POWER_STAGE = {
    "0": "off",
    "1": "minimum",
    "2": "intermediate",
    "3": "maximum",
}

BURNER_STATUS_DETAIL = {
    "0": "stop",
    "1": "ignition",
    "2": "fuel_priming",
    "3": "ignition_stabilisation",
    "4": "heating_stabilisation",
    "5": "heating",
    "6": "extinguishing",
    "7": "burner_cleaning",
    "10": "positioning",
    "11": "leak_test",
    "12": "fuel_dose",
    "13": "igniter_warm_up",
    "14": "fuel_ignition",
    "15": "fuel_top_up",
    "16": "post_ignition_blow",
    "100": "ignition_failed",
    "101": "heating_failed_101",
    "102": "heating_failed_102",
    "103": "heating_failed_103",
    "104": "extinguished_after_priming",
    "105": "extinguished_during_ignition",
    "106": "extinguished_during_stabilisation",
    "107": "extinguished_during_operation",
}

CURATED: Mapping[str, Curated] = {
    # Temperatures
    "tkot_value": _temperature("water_temperature"),
    "tpow_value": _temperature("return_temperature"),
    "tcwu_value": _temperature("dhw_temperature"),
    "tzew_value": _temperature("outdoor_temperature"),
    "t1_value": _temperature("mixing_valve_temperature"),
    "tsp_value": _temperature("flue_gas_temperature"),
    "temp_tank_hi": _temperature("buffer_top_temperature"),
    "temp_tank_lo": _temperature("buffer_bottom_temperature"),
    # Coal controllers measure the temperature of the screw feeder itself: it rising
    # is how burn-back into the hopper shows up.
    "tpod_value": _temperature("feeder_temperature"),
    "twew_value": _temperature("indoor_temperature"),
    # The feeder of a pellet burner module, a different sensor than tpod_value.
    "mpl_temp": _temperature("burner_feeder_temperature"),
    "ob1_pok_tact": _temperature("room_temperature"),
    # Setpoints currently in force (schedules and weather curves already applied)
    "kot_tact": _temperature("active_setpoint"),
    "cwu_tact": _temperature("dhw_active_setpoint"),
    "ob1_zaw4d_tzad": _temperature("mixing_valve_active_setpoint"),
    "ob1_pok_tzad": _temperature("room_active_setpoint"),
    "ob1_zaw4d_pos": _measurement("mixing_valve_position"),
    # Boiler and burner
    "kot_status": _enum("status", {"0": "off", "1": "standby", "2": "heating"}),
    "pl_status": _enum("burner_status", BURNER_STATUS),
    "pl_status_ext": _enum("burner_status_detail", BURNER_STATUS_DETAIL),
    "pl_power_kw": _measurement("burner_power", device_class=SensorDeviceClass.POWER),
    "pl_power": _enum("burner_power_stage", BURNER_POWER_STAGE),
    "pl_flame": _measurement("flame"),
    "pl_fuel_flow": _measurement("fuel_flow"),
    "act_dm_speed": _measurement("fan_power"),
    "mpl_dm_rpm": _measurement("fan_speed"),
    "dp_value": _measurement("pressure_difference", device_class=SensorDeviceClass.PRESSURE),
    "fuel_fill": _measurement("feeding"),
    "pl_plimit_state": _measurement("power_limit"),
    "pl_tfire": Curated(
        key="ignition_count", platform=Platform.SENSOR, state_class=TOTAL_INCREASING
    ),
    "pl_tptotal": Curated(
        key="burner_runtime",
        platform=Platform.SENSOR,
        device_class=DURATION,
        state_class=TOTAL_INCREASING,
        suggested_unit=UnitOfTime.HOURS,
    ),
    "fire_time": _measurement("last_ignition_duration", device_class=DURATION),
    # Fuel
    "fuel_level": _measurement("fuel_level"),
    # The controller recalculates this estimate on every read; unrounded, the state would
    # change with each poll and flood the recorder and the logbook.
    "next_fuel_time": Curated(
        key="next_refuel",
        platform=Platform.SENSOR,
        device_class=SensorDeviceClass.TIMESTAMP,
        resolution=SECONDS_PER_HOUR,
    ),
    "add_fuel_time": Curated(
        key="last_refuel", platform=Platform.SENSOR, device_class=SensorDeviceClass.TIMESTAMP
    ),
    "pod_run_time": Curated(
        key="feeder_runtime",
        platform=Platform.SENSOR,
        device_class=DURATION,
        state_class=TOTAL_INCREASING,
        unit=UnitOfTime.SECONDS,
        suggested_unit=UnitOfTime.MINUTES,
    ),
    "clean_act_kg": Curated(
        key="pellets_since_cleaning",
        platform=Platform.SENSOR,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=TOTAL_INCREASING,
    ),
    # Modes
    "tryb_auto_state": _enum("operating_mode", {"0": "manual", "1": "automatic", "2": "alarm"}),
    "zima_lato_state": _enum("season", {"0": "winter", "1": "summer"}),
    "cwu_out_state": _enum(
        "dhw_heating_status", {"0": "off", "1": "heating", "2": "priority_heating"}
    ),
    "out_zaw4d": _enum("mixing_valve_action", {"0": "stop", "1": "opening", "2": "closing"}),
    # Power outputs
    "out_pomp1": _output("pump_1"),
    "out_pomp2": _output("pump_2"),
    "out_cwu": _output("dhw_pump"),
    "out_miesz": _output("auxiliary_pump"),
    "out_tank": _output("buffer_pump"),
    "out_pod": _output("feeder"),
    "out_dm": _output("fan"),
    "out_aux": _output("auxiliary_output"),
    "out_clean_wym": _output("exchanger_cleaning"),
    "mpl_feed": _output("stoker"),
    "mpl_heat": _output("igniter"),
    "mpl_clean": _output("burner_cleaning"),
    # Binary inputs
    "di_term1": _input("thermostat_1"),
    "di_term2": _input("thermostat_2", enabled=False),
    "di_zawl": _input("grate_position"),
    "di_zas": _input("hopper_sensor"),
    "di_alarm": _input("external_alarm_input"),
    "ob1_pok_heat": _input("room_heating_demand"),
    # Control
    "kot_tzad": _setpoint("setpoint"),
    "cwu_tzad": _setpoint("dhw_setpoint"),
    "tank_tzad": _setpoint("buffer_setpoint"),
    "ob1_tzad": _setpoint("mixing_valve_setpoint"),
    "ob1_pok_lo": _setpoint("room_temperature_low"),
    "ob1_pok_norm": _setpoint("room_temperature_normal"),
    "ob1_pok_hi": _setpoint("room_temperature_comfort"),
    "zima_lato": Curated(
        key="season_mode",
        platform=Platform.SELECT,
        options={"0": "winter", "1": "summer", "2": "auto_summer"},
    ),
    "cwu_state": Curated(
        key="dhw_mode",
        platform=Platform.SELECT,
        options={"0": "off", "1": "schedule", "2": "on", "3": "plus_1h", "4": "plus_2h"},
    ),
    "cmd_ackalarm": Curated(key="acknowledge_alarms", platform=Platform.BUTTON),
    "cmd_reset": Curated(
        key="restart", platform=Platform.BUTTON, enabled=False, category=EntityCategory.CONFIG
    ),
}

# Registers of radio nodes and rooms, shared by all node types.
NODE_CURATED: Mapping[str, Curated] = {
    "temp": _temperature("temperature"),
    "rh": _measurement("humidity", device_class=SensorDeviceClass.HUMIDITY),
    "bat": _measurement(
        "battery", device_class=SensorDeviceClass.BATTERY, category=EntityCategory.DIAGNOSTIC
    ),
    "sig": _measurement("signal", category=EntityCategory.DIAGNOSTIC),
}

# Registers the controller reports but leaves out of its dictionary.
EXTRA_REGISTERS: Mapping[str, RegisterDef] = {
    "pl_power": RegisterDef(
        tid="pl_power",
        type=TYPE_ENUM,
        priv="rrrrr",
        options=tuple(RegisterOption(id=value, labels={}) for value in BURNER_POWER_STAGE),
    ),
    "clean_act_kg": RegisterDef(
        tid="clean_act_kg", type="float", priv="rrrrr", unit="kg", precision=1
    ),
    # Whether the room regulator of circuit 1 calls for heat; when it does not, the controller
    # lowers the mixing valve setpoint by ob1_tobn.
    "ob1_pok_heat": RegisterDef(
        tid="ob1_pok_heat",
        type=TYPE_ENUM,
        priv="rrrrr",
        options=(RegisterOption(id="0", labels={}), RegisterOption(id="1", labels={})),
    ),
}

# Identity, clock and network settings: shown as device details or of no use as entities.
EXCLUDED_PREFIXES = ("auth_", "eth_", "device_")
EXCLUDED = frozenset(
    {"datetime", "localtimezone", "accesslevel", "install_type", "wnd_cfg", "fuel_level_enum"}
)
NODE_EXCLUDED = frozenset({"s", "t", "v", "name", "enable", "relays", "hb0", "hb1", "room_id"})

_CIRCUIT_PREFIX_LENGTH = len("ob1_")


def _circuit_active(tid: str, snapshot: Snapshot) -> bool:
    """Tell whether the heating circuit a register belongs to is configured."""
    prefix = tid[:_CIRCUIT_PREFIX_LENGTH]
    if not (prefix.startswith("ob") and prefix[2:3].isdigit() and prefix.endswith("_")):
        return True
    return snapshot.value(MAIN_VID, f"{prefix}typ") not in (None, "0")


def _charted(register: RegisterDef) -> bool:
    """Tell whether the controller plots this register in its own web panel."""
    return API_CHART in register.api.split("|")


def _fits(register: RegisterDef, curated: Curated) -> bool:
    """Tell whether a curated entry still matches what the controller's dictionary says."""
    if curated.platform is Platform.BUTTON:
        return register.type == TYPE_COMMAND
    if curated.platform is Platform.NUMBER:
        has_range = register.minimum is not None and register.maximum is not None
        return register.type in NUMERIC_TYPES and has_range
    if curated.platform is Platform.SELECT or curated.options is not None:
        known = {option.id for option in register.options}
        return register.type == TYPE_ENUM and set(curated.options or ()) <= known
    if curated.platform is Platform.BINARY_SENSOR:
        return register.type == TYPE_ENUM
    if curated.device_class == SensorDeviceClass.TIMESTAMP:
        return register.type == TYPE_TIMESTAMP
    return register.type in NUMERIC_TYPES


def _as_sensor(curated: Curated) -> Curated:
    """Present a setting that may not be changed as a sensor under the same key."""
    if curated.platform is Platform.SELECT:
        return replace(curated, platform=Platform.SENSOR, device_class=SensorDeviceClass.ENUM)
    return replace(
        curated,
        platform=Platform.SENSOR,
        device_class=TEMPERATURE,
        state_class=MEASUREMENT,
    )


def _default_platform(register: RegisterDef) -> Platform | None:
    """Registers outside the curated set are only ever shown, never changed."""
    if register.type == TYPE_ALARM:
        return Platform.BINARY_SENSOR
    if register.type in NUMERIC_TYPES or register.type in (TYPE_ENUM, TYPE_TIMESTAMP):
        return Platform.SENSOR
    return None


def _spec(
    vid: int,
    register: RegisterDef,
    curated: Curated | None,
    access_level: int,
    read_only: bool,
) -> EntitySpec | None:
    if curated is not None and not _fits(register, curated):
        # Another firmware redefined the register; fall back to what the dictionary says.
        curated = None

    if curated is None:
        platform = _default_platform(register)
        if platform is None:
            return None
        measured = _charted(register)
        enabled = measured or register.type == TYPE_ALARM
        category = None if measured else EntityCategory.DIAGNOSTIC
        return EntitySpec(vid, register, platform, None, enabled, category)

    access = register.access(access_level)
    if curated.platform is Platform.BUTTON:
        if read_only or access != ACCESS_EXECUTE:
            return None
    elif curated.platform in CONTROL_PLATFORMS and (read_only or access != ACCESS_WRITE):
        curated = _as_sensor(curated)

    return EntitySpec(vid, register, curated.platform, curated, curated.enabled, curated.category)


def is_node_active(vdev: VirtualDevice, values: Mapping[str, str]) -> bool:
    """Tell whether a radio node or room slot is in use."""
    if ROOM_DEVICE_TYPE in vdev.types:
        return bool(values.get("name") or values.get("temp"))
    return values.get("s") == "1"


def active_nodes(dictionary: Dictionary, snapshot: Snapshot) -> list[int]:
    """Return the slots, other than the controller, that are in use."""
    return [
        vid
        for vid, device in snapshot.devices.items()
        if vid != MAIN_VID
        and (vdev := dictionary.vdevs.get(vid)) is not None
        and is_node_active(vdev, device.values)
    ]


def build_specs(
    dictionary: Dictionary,
    snapshot: Snapshot,
    access_level: int,
    read_only: bool,
) -> list[EntitySpec]:
    """Decide which entities to create for the registers the controller reports."""
    specs: list[EntitySpec] = []

    controller = snapshot.devices[MAIN_VID].values
    registers = {**dictionary.registers_for(MAIN_VID), **EXTRA_REGISTERS}
    for tid, register in registers.items():
        if tid in EXCLUDED or tid.startswith(EXCLUDED_PREFIXES):
            continue
        # Commands have no value, every other register must actually be reported.
        if register.type != TYPE_COMMAND and tid not in controller:
            continue
        if not _circuit_active(tid, snapshot):
            continue
        spec = _spec(MAIN_VID, register, CURATED.get(tid), access_level, read_only)
        if spec is not None:
            specs.append(spec)

    for vid in active_nodes(dictionary, snapshot):
        values = snapshot.devices[vid].values
        for tid, register in dictionary.registers_for(vid).items():
            if tid in NODE_EXCLUDED or tid not in values:
                continue
            spec = _spec(vid, register, NODE_CURATED.get(tid), access_level, read_only)
            if spec is not None:
                specs.append(spec)

    return specs
