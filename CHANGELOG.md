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
- The register dictionary is unpacked when the controller gzips it without
  saying so in `Content-Encoding`, which eCoal firmware does.
- `scripts/probe.py` dumps the controller's identity, dictionary and current
  values, to work out what a given firmware exposes;
  `scripts/analyse_dump.py` runs such a dump through the catalog and reports
  the entities it would produce.

Verified against an eCoal controller, hardware 3.5, firmware 1.1.38.12, fitted
to an Ogniwo Eko Plus+ 38 kW: 384 registers in the dictionary, 178 entities, 71
of them enabled by default.

A read-only panel account works: firmware serves `info.cgi` to root only, so
the controller is identified from its own registers when that endpoint refuses
the account. The MAC is the same one either way, so an entry stays tied to the
same controller whichever account configured it, and the access level alone
then decides that nothing is writable.
