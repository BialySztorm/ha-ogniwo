"""Errors raised while talking to a Ogniwo controller."""


class OgniwoError(Exception):
    """Base error of the Ogniwo client."""


class OgniwoConnectionError(OgniwoError):
    """The controller could not be reached or answered with an HTTP error."""


class OgniwoInvalidHostError(OgniwoError):
    """The configured host is not a usable host name or address."""


class OgniwoAuthError(OgniwoError):
    """The controller rejected the credentials."""


class OgniwoParseError(OgniwoError):
    """The controller answered with something that could not be understood."""


class OgniwoWriteError(OgniwoError):
    """The controller refused to change a register."""
