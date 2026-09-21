"""Device and protocol constants for Razer Tartarus V2."""

from __future__ import annotations

USB_VID = 0x1532
USB_PID = 0x022B
DEVICE_NAME = "Razer Tartarus V2"

# USB control transfer (matches OpenRazer keyboard path for this PID)
REPORT_VALUE = 0x0300
REPORT_INDEX = 0x01  # default for Tartarus V2 (not in special-case list)
WAIT_SECONDS = 0.005
MAX_RETRIES = 5

# Report framing
REPORT_LEN = 90
TX_ID_EFFECTS = 0x1F
TX_ID_BREATH = 0x3F  # Tartarus V2 quirk in OpenRazer
TX_ID_PROFILE_LED = 0xFF

VARSTORE = 0x01
ZERO_LED = 0x00
BACKLIGHT_LED = 0x05
MACRO_LED = 0x07
GAME_LED = 0x08
RED_PROFILE_LED = 0x0C
GREEN_PROFILE_LED = 0x0D
BLUE_PROFILE_LED = 0x0E

MATRIX_ROWS = 4
MATRIX_COLS = 6

# Response status codes
CMD_BUSY = 0x01
CMD_SUCCESS = 0x02
CMD_FAILURE = 0x03
CMD_TIMEOUT = 0x04
CMD_NOT_SUPPORTED = 0x05

DRIVER_MODE = 0x03
NORMAL_MODE = 0x00

# Cache / log paths (expanded at runtime)
CACHE_DIR_NAME = "tartarus-v2"
LOG_FILE_NAME = "tartarus-v2.log"
DEFAULT_PROFILE_NAME = "default"
