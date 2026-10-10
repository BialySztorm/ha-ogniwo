#!/usr/bin/env python3
"""Ask a controller what it exposes, without Home Assistant in the way.

Run this against the boiler before reporting that the integration does not work:
it tells which of the two HTTP APIs the controller speaks, and writes down the
register dictionary and the current values so the catalog can be matched to the
firmware at hand.

    python scripts/probe.py 192.168.1.50 --username root --password secret

Anything not passed is taken from `.env` next to this repository, which saves
quoting a password with shell metacharacters in it:

    OGNIWO_HOST=192.168.1.50
    OGNIWO_USERNAME=root
    OGNIWO_PASSWORD=secret

The dump lands in ./probe-<host>/ and holds no credentials: the registers that
carry the panel passwords are dropped, the rest is left as the controller sent
it, so read it before sharing.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import gzip
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REGISTER_PATHS = {
    "info.xml": "info.cgi",
    "hardware.xml": "config/hardware.xml",
    "syncvalues.txt": "syncvalues.cgi",
}
LEGACY_STATUS_FRAME = "02010006000000006103"
GZIP_MAGIC = b"\x1f\x8b"
SECRET_PREFIX = "auth_"
TIMEOUT = 20

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
ENV_HOST = "OGNIWO_HOST"
ENV_USERNAME = "OGNIWO_USERNAME"
ENV_PASSWORD = "OGNIWO_PASSWORD"


def read_env(path: Path) -> dict[str, str]:
    """Read the KEY=VALUE lines of an .env file; missing file means no settings."""
    if not path.is_file():
        return {}
    settings = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if separator:
            # Quotes are what a shell would have eaten, so eat them here too.
            settings[key.strip()] = value.strip().strip("\"'")
    return settings


def setting(key: str, given: str | None, env: dict[str, str]) -> str | None:
    """Resolve one setting: what was passed wins over .env, which wins over the shell."""
    return given or env.get(key) or os.environ.get(key)


def fetch(host: str, path: str, auth: str, query: dict[str, str] | None = None) -> bytes:
    """GET one path from the controller; raise urllib's error as it comes."""
    url = f"http://{host}/{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read()
    # The register dictionary is served gzipped; urllib, unlike aiohttp, keeps it that way.
    return gzip.decompress(body) if body.startswith(GZIP_MAGIC) else body


def redact(values: bytes) -> bytes:
    """Drop the registers that carry the credentials of the web panel."""
    lines = []
    for line in values.decode("utf-8", errors="replace").split("\r"):
        kept = [part for part in line.split(";") if not part.startswith(SECRET_PREFIX)]
        lines.append(";".join(kept))
    return "\r".join(lines).encode()


def summarise(syncvalues: bytes) -> dict[str, str]:
    """Pull the identity of the controller out of its own values."""
    interesting = ("device_type", "device_soft_version", "device_hard_version", "accesslevel")
    found = {}
    for part in syncvalues.decode("utf-8", errors="replace").split(";"):
        tid, separator, value = part.partition(":")
        if separator and tid in interesting:
            found[tid] = value
    return found


def probe_register_api(host: str, auth: str, out: Path) -> bool:
    """Try the modern register API and save whatever answers."""
    served = {}
    for name, path in REGISTER_PATHS.items():
        try:
            body = fetch(host, path, auth)
        except urllib.error.HTTPError as err:
            print(f"  {path}: HTTP {err.code}")
            continue
        except OSError as err:
            print(f"  {path}: {err}")
            continue
        if name == "syncvalues.txt":
            body = redact(body)
        (out / name).write_bytes(body)
        served[name] = len(body)
        print(f"  {path}: {len(body)} bytes -> {out / name}")

    if "syncvalues.txt" in served:
        identity = summarise((out / "syncvalues.txt").read_bytes())
        (out / "identity.json").write_text(json.dumps(identity, indent=2))
        print(f"  controller: {identity or 'not reported'}")
    return len(served) == len(REGISTER_PATHS)


def probe_legacy_api(host: str, auth: str, out: Path) -> bool:
    """Try the old byte-frame protocol used by firmware without the register API."""
    try:
        body = fetch(host, "", auth, {"com": LEGACY_STATUS_FRAME})
    except (OSError, urllib.error.HTTPError) as err:
        print(f"  /?com=: {err}")
        return False
    text = body.decode("utf-8", errors="replace").strip()
    if not text.startswith("["):
        print(f"  /?com=: answered {len(body)} bytes, not a byte frame")
        return False
    (out / "legacy-status.txt").write_bytes(body)
    print(f"  /?com=: byte frame of {text.count(',') + 1} values -> {out / 'legacy-status.txt'}")
    return True


def main() -> int:
    """Probe the controller and report which API it speaks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", help=f"address of the controller, or ${ENV_HOST}")
    parser.add_argument("--username", help=f"panel account, or ${ENV_USERNAME}")
    parser.add_argument("--password", help=f"its password, or ${ENV_PASSWORD}")
    parser.add_argument("--out", type=Path, help="directory for the dump")
    args = parser.parse_args()

    env = read_env(ENV_FILE)
    host = setting(ENV_HOST, args.host, env)
    if not host:
        parser.error(f"no host given and none in {ENV_FILE}")
    username = setting(ENV_USERNAME, args.username, env) or "root"
    password = setting(ENV_PASSWORD, args.password, env)
    if password is None:
        password = getpass.getpass(f"Password of {username} on {host}: ")

    out = args.out or Path(f"probe-{host.replace(':', '_')}")
    out.mkdir(parents=True, exist_ok=True)
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()

    print(f"Register API on {host}:")
    modern = probe_register_api(host, auth, out)
    print(f"Legacy byte protocol on {host}:")
    legacy = probe_legacy_api(host, auth, out)

    print()
    if modern:
        print("This controller speaks the register API: the integration should work.")
    elif legacy:
        print(
            "This controller speaks only the legacy byte protocol. The integration "
            "cannot drive it yet; send the dump so a client for it can be written."
        )
    else:
        print(
            "Neither API answered. Check the address, that the panel is reachable "
            "over HTTP, and the username and password of its local account."
        )
    return 0 if modern or legacy else 1


if __name__ == "__main__":
    sys.exit(main())
