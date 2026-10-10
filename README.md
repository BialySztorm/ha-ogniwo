# Ogniwo for Home Assistant

A local Home Assistant integration for the **eCoal.pl** controllers fitted to
Ogniwo boilers (developed for an *Eko Plus+ 38 kW*). It talks to the
controller's own web panel over the local network; no cloud account, no
eSterownik.pl server.

## Why another integration

eCoal controllers serve two different HTTP interfaces, and which one you get
depends on the firmware:

| | Endpoint | Used by |
|---|---|---|
| Old, binary | `GET /?com=<hex frame>` → array of bytes at fixed offsets | `ecoaliface`, so Home Assistant's built-in `ecoal_boiler`; also `dkuku/ecoal-ha` |
| Current, register-based | `info.cgi`, `config/hardware.xml`, `syncvalues.cgi`, `setregister.cgi` | `mcflypl/ha-pello`, and this integration |

The binary interface is why the existing integrations are brittle:
`ecoaliface` refuses firmware outside the versions it knows, and a byte map
written for one firmware silently decodes garbage on another, because the
offsets move.

This integration uses the register interface instead, where **the controller
publishes its own register dictionary** — names, units, ranges, enum options
and access rights. Nothing is hardcoded to a firmware version, so a controller
whose register map nobody has seen before still produces sensible entities.

## Requirements

- Home Assistant 2026.9 or newer.
- A controller that answers `syncvalues.cgi` — i.e. one with the register API.
  If yours only answers `/?com=`, see [Checking your controller](#checking-your-controller).
- The address of the controller's web panel and a local account on it.

## Installation

### HACS

Add `https://github.com/BialySztorm/ha-ogniwo` as a custom repository of
category *Integration*, install
*Ogniwo*, restart Home Assistant, then add the integration from
**Settings → Devices & services**.

### Manually

Copy `custom_components/ogniwo` into your `config/custom_components/`, restart
Home Assistant, and add the integration.

## Configuration

Setup asks for the host, username and password of the local web panel. Options
afterwards:

- **Polling interval** — 10 to 600 seconds, 30 by default.
- **Read-only mode** — never write to the controller; settings appear as
  sensors instead of as numbers and selects.

A read-only account of the panel is enough, and is the safest way to run this:
nothing writable is created for it at all. Firmware serves `info.cgi` to root
only, so with such an account the controller is identified from its own
registers instead — the same MAC, hence the same entry either way.

The account's access level decides what may be changed: a register the
controller does not let that account write is shown as a sensor. Only a short,
reviewed list of settings is writable at all — setpoints for boiler, hot water,
buffer, mixing valve and room, season and hot water mode, alarm acknowledgement
and restart. Everything else is read-only here regardless of access level.

## Entities

Three kinds of entity come out of the register dictionary:

1. **Curated registers** — stable English entity ids, device classes, Polish and
   English names, enabled by default. Temperatures, setpoints, boiler and burner
   state, fuel, pumps and feeder outputs, binary inputs, alarms.
2. **Registers the controller charts** (`api="|chart|"` in the dictionary) —
   enabled by default, named by the controller in your Home Assistant language.
   This is what makes an unknown firmware useful out of the box: the controller
   itself marks which registers are measurements worth plotting. Values reported
   in °C are presented as temperatures.
3. **Everything else** — hysteresis, PID terms, timings and the rest of the
   configuration parameters. Created disabled; enable the ones you want in the
   entity settings.

Each alarm register becomes a problem binary sensor listing the active
conditions in its attributes, plus one summary `Alarm` sensor over all of them.

## Checking your controller

If setup fails, or entities look wrong, ask the controller directly:

```
python scripts/probe.py 192.168.1.50 --username root --password secret
```

It reports which of the two APIs answers and writes the controller's identity,
register dictionary and current values to `probe-<host>/`. The dump drops the
registers holding the panel passwords, but read it before sharing it: it still
contains your network settings and heating schedules.

Copy `.env.example` to `.env` to keep the address and credentials out of the
command line — handy on PowerShell, where a password containing `$` is
expanded before the script ever sees it:

```
python scripts/probe.py
```

To see what the integration would make of a dump — how many entities, which
curated registers your controller lacks, what each one currently reads — run
the dump through the catalog:

```
python scripts/analyse_dump.py probe-192.168.1.50
```

That one imports the integration, so it needs the test dependencies from
`requirements_test.txt` (or the `Dockerfile.test` image).

A controller that only answers `/?com=` cannot be driven by this integration
yet; the probe dump is what a client for the old protocol would be written
from.

## Security

The controller speaks plain HTTP with basic authentication, and its
`syncvalues.cgi` response includes the panel credentials of every access level
(this integration drops them on parse, and leaves them out of diagnostics and
probe dumps). Keep the controller on a network you trust.

## Credits

Derived from [ha-pello](https://github.com/mcflypl/ha-pello) by @mcflypl, which
implements the same register API for the Pello pellet controllers of the same
manufacturer. The protocol notes in
[dkuku/ecoal-ha](https://github.com/dkuku/ecoal-ha) documented the old binary
interface this integration deliberately avoids. Both are Apache-2.0; see
`NOTICE`.

## License

Apache License 2.0.
