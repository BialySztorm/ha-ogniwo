"""Constants for the Ogniwo integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ogniwo"

CONF_READ_ONLY: Final = "read_only"

DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 600

REQUEST_TIMEOUT: Final = 15

# Virtual device id of the controller itself; radio nodes and rooms use higher ids.
MAIN_VID: Final = 0

# The controller keeps reporting the last value of a radio node that went silent.
STALE_AFTER: Final = timedelta(minutes=30)

# Least privileged level, assumed when the controller does not report one.
ACCESS_LEVEL_USER: Final = 2
