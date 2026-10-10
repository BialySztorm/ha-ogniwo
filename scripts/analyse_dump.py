#!/usr/bin/env python3
"""Report what the integration would make of a probe dump.

Point it at a directory written by probe.py and it prints how many entities
each platform would get, which curated registers the controller does not have,
and which of its charted registers end up named by the controller alone:

    python scripts/analyse_dump.py probe-192.168.0.164

It needs the Home Assistant packages the tests use, so run it the same way:
inside the test image, not against the plain interpreter.
"""

from __future__ import annotations

import argparse
import gzip
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.ogniwo.catalog import CURATED, active_nodes, build_specs
from custom_components.ogniwo.parser import (
    parse_dictionary,
    parse_info,
    parse_snapshot,
)

MAIN_VID = 0
# What the integration falls back to when the controller reports no level.
ACCESS_LEVEL_USER = 2


def access_level(snapshot) -> int:
    """Read the access level of the account the dump was taken with."""
    try:
        return int(snapshot.value(MAIN_VID, "accesslevel") or "")
    except ValueError:
        return ACCESS_LEVEL_USER


def read(path: Path) -> str:
    """Read a dumped response, unpacking the gzip an older probe left packed."""
    body = path.read_bytes()
    if body.startswith(b"\x1f\x8b"):
        body = gzip.decompress(body)
    return body.decode("utf-8", errors="replace")


def main() -> int:
    """Print the entity breakdown of one dump."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path, help="directory written by probe.py")
    parser.add_argument(
        "--read-only", action="store_true", help="as if the read-only option were on"
    )
    args = parser.parse_args()

    info = parse_info(read(args.dump / "info.xml"))
    dictionary = parse_dictionary(read(args.dump / "hardware.xml"))
    snapshot = parse_snapshot(read(args.dump / "syncvalues.txt"))

    print(
        f"{info.name}: {info.hardware_type} "
        f"hv {info.hardware_version} sv {info.software_version}"
    )
    level = access_level(snapshot)
    print(f"registers in the dictionary: {len(dictionary.registers_for(0))}")
    print(f"access level of the account used: {level}")
    print(f"active device slots: {active_nodes(dictionary, snapshot)}")

    specs = build_specs(dictionary, snapshot, level, read_only=args.read_only)
    platforms = Counter(spec.platform.value for spec in specs)
    print(f"entities: {len(specs)} -> {dict(sorted(platforms.items()))}")
    print(f"enabled by default: {sum(1 for spec in specs if spec.enabled)}")

    base = {spec.register.tid: spec for spec in specs if spec.vid == 0}
    print(f"curated registers this controller lacks: {sorted(set(CURATED) - set(base)) or 'none'}")

    named = [spec for spec in base.values() if spec.curated is not None]
    print(f"\ncurated entities ({len(named)}):")
    for spec in sorted(named, key=lambda spec: spec.key):
        unit = f" [{spec.register.unit}]" if spec.register.unit else ""
        value = snapshot.value(0, spec.register.tid)
        print(f"  {spec.platform.value:<14} {spec.key:<28}{unit} = {value}")

    charted = [spec for spec in base.values() if spec.curated is None and spec.enabled]
    print(f"\nenabled on the controller's own charting hint ({len(charted)}):")
    for spec in sorted(charted, key=lambda spec: spec.register.tid):
        unit = f" [{spec.register.unit}]" if spec.register.unit else ""
        value = snapshot.value(0, spec.register.tid)
        print(f"  {spec.register.tid:<18} {spec.register.name('en') or '?'}{unit} = {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
