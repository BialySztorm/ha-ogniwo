"""HTTP client of an Ogniwo boiler controller."""

from __future__ import annotations

import gzip
import re
from http import HTTPStatus

import aiohttp
from yarl import URL

from .const import REQUEST_TIMEOUT
from .errors import (
    OgniwoAuthError,
    OgniwoConnectionError,
    OgniwoError,
    OgniwoInvalidHostError,
    OgniwoParseError,
    OgniwoWriteError,
)
from .models import ControllerInfo, Dictionary, Snapshot
from .parser import (
    parse_dictionary,
    parse_identity,
    parse_info,
    parse_snapshot,
    parse_write_result,
)

PATH_INFO = "info.cgi"
PATH_DICTIONARY = "config/hardware.xml"
PATH_VALUES = "syncvalues.cgi"
PATH_WRITE = "setregister.cgi"
# The panel root, where firmware too old for the register API answers byte frames.
PATH_LEGACY = ""

# Read-status frame of that old byte protocol, sent only to tell the two APIs apart.
LEGACY_STATUS_FRAME = "02010006000000006103"
GZIP_MAGIC = b"\x1f\x8b"

# The register dictionary, the largest response, is about 320 kB.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 64 * 1024

_REGISTER_ID = re.compile(r"^[A-Za-z0-9_]+$")
_REGISTER_VALUE = re.compile(r"^-?\d+(\.\d+)?$")
# The old protocol answers with the frame it echoes back, as an array of bytes.
_LEGACY_RESPONSE = re.compile(r"^\[\s*2\s*,")


class OgniwoClient:
    """Reads and changes registers of a Ogniwo controller over its local HTTP API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
    ) -> None:
        try:
            self._base = URL.build(scheme="http", host=host)
            authorization = aiohttp.encode_basic_auth(username, password)
        except ValueError as err:
            # The original message would repeat the input, which may hold a password.
            raise OgniwoInvalidHostError("Invalid host or username") from err
        self._session = session
        self._headers = {"Authorization": authorization}
        self._timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    @property
    def base_url(self) -> str:
        """URL of the controller's own web panel."""
        return str(self._base)

    async def _read(self, response: aiohttp.ClientResponse) -> str:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.content.iter_chunked(CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise OgniwoParseError("Response of the controller is too large")
            chunks.append(chunk)
        body = b"".join(chunks)
        # The dictionary is served gzipped; firmware that omits Content-Encoding
        # leaves aiohttp no reason to unpack it.
        if body.startswith(GZIP_MAGIC):
            try:
                body = gzip.decompress(body)
            except (OSError, EOFError) as err:
                raise OgniwoParseError("Controller sent a damaged gzip response") from err
        return body.decode("utf-8", errors="replace")

    async def _get(self, path: str, query: dict[str, str | int] | None = None) -> str:
        url = self._base / path
        if query is not None:
            url = url.with_query(query)
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=self._timeout, allow_redirects=False
            ) as response:
                if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                    raise OgniwoAuthError("Controller rejected the credentials")
                if response.status != HTTPStatus.OK:
                    raise OgniwoConnectionError(f"{path} answered with HTTP {response.status}")
                return await self._read(response)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise OgniwoConnectionError(f"Request to {path} failed: {err}") from err

    async def async_get_info(self) -> ControllerInfo:
        """Read the identity of the controller.

        Firmware serves info.cgi to root only, so an account allowed to read
        every register still gets 403 there. When that happens the identity is
        taken from the registers instead; if those do not identify the
        controller either, the refusal stands and is reported as what it is.
        """
        try:
            return parse_info(await self._get(PATH_INFO))
        except OgniwoAuthError:
            # Credentials that are simply wrong fail here too, and re-raise.
            identity = parse_identity(await self.async_get_snapshot())
            if identity is None:
                raise
            return identity

    async def async_get_dictionary(self) -> Dictionary:
        """Read the register dictionary."""
        return parse_dictionary(await self._get(PATH_DICTIONARY))

    async def async_get_snapshot(self) -> Snapshot:
        """Read the current values of all registers of all device slots."""
        return parse_snapshot(await self._get(PATH_VALUES))

    async def async_speaks_legacy_api(self) -> bool:
        """Tell whether the controller only offers the old byte-frame protocol.

        Firmware older than the register API answers `/?com=<frame>` with an array
        of bytes and knows nothing of the endpoints above. Telling that apart from
        an unreachable controller is the difference between a useful message and
        "cannot connect".
        """
        try:
            body = await self._get(PATH_LEGACY, {"com": LEGACY_STATUS_FRAME})
        except OgniwoError:
            return False
        return _LEGACY_RESPONSE.match(body.strip()) is not None

    async def async_set_register(self, vid: int, tid: str, value: str) -> None:
        """Change one register. Raises OgniwoWriteError when the controller refuses."""
        # Anything else could smuggle a second register into the request.
        if not _REGISTER_ID.match(tid) or not _REGISTER_VALUE.match(value):
            raise OgniwoWriteError(f"Refusing to write an unexpected value to {tid!r}")
        # The controller expects the device first, then the register.
        response = await self._get(PATH_WRITE, {"device": vid, tid: value})
        parse_write_result(response, tid)
