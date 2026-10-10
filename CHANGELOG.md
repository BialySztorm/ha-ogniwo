# Changelog

## [0.1.0] - 2026-10-10

First release. Derived from [ha-pello](https://github.com/mcflypl/ha-pello),
retargeted at the eCoal.pl controllers fitted to Ogniwo boilers.

- Reads every register the controller publishes in its own dictionary, so the
  integration does not depend on a known firmware version or byte layout.
- Entities the controller charts in its web panel are enabled by default; the
  remaining registers are created disabled.
- Registers reported in °C are presented as temperatures even when they are not
  in the curated list.
- Curated entries for the sensors of a coal boiler: feeder and indoor
  temperature.
- The config flow reports a controller that only speaks the old byte protocol
  as such, instead of as a connection failure.
- `scripts/probe.py` dumps the controller's identity, dictionary and current
  values, to work out what a given firmware exposes.
