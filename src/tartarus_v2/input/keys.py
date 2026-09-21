"""Physical key table for Tartarus V2 (Linux EV_KEY codes the device emits)."""

from __future__ import annotations

# Logical name -> default Linux keycode emitted by the firmware/HID stack.
# Derived from OpenRazer TARTARUS_EVENT_MAPPING (inverted) plus scroll extras.
LOGICAL_TO_CODE: dict[str, int] = {
    "key_01": 15,   # KEY_TAB
    "key_02": 16,   # KEY_Q
    "key_03": 17,   # KEY_W
    "key_04": 18,   # KEY_E
    "key_05": 19,   # KEY_R
    "key_06": 58,   # KEY_CAPSLOCK
    "key_07": 30,   # KEY_A
    "key_08": 31,   # KEY_S
    "key_09": 32,   # KEY_D
    "key_10": 33,   # KEY_F
    "key_11": 42,   # KEY_LEFTSHIFT
    "key_12": 44,   # KEY_Z
    "key_13": 45,   # KEY_X
    "key_14": 46,   # KEY_C
    "key_15": 47,   # KEY_V
    "mode": 56,     # KEY_LEFTALT / MODE_SWITCH
    "thumb": 57,    # KEY_SPACE
    "stick_up": 103,
    "stick_left": 105,
    "stick_right": 106,
    "stick_down": 108,
}

CODE_TO_LOGICAL: dict[int, str] = {v: k for k, v in LOGICAL_TO_CODE.items()}

# Friendly names for common output keycodes (subset; remapper also accepts names via evdev.ecodes)
OUTPUT_ALIASES: dict[str, str] = {
    "ctrl": "KEY_LEFTCTRL",
    "lctrl": "KEY_LEFTCTRL",
    "rctrl": "KEY_RIGHTCTRL",
    "shift": "KEY_LEFTSHIFT",
    "lshift": "KEY_LEFTSHIFT",
    "rshift": "KEY_RIGHTSHIFT",
    "alt": "KEY_LEFTALT",
    "lalt": "KEY_LEFTALT",
    "ralt": "KEY_RIGHTALT",
    "super": "KEY_LEFTMETA",
    "meta": "KEY_LEFTMETA",
    "win": "KEY_LEFTMETA",
    "space": "KEY_SPACE",
    "enter": "KEY_ENTER",
    "return": "KEY_ENTER",
    "esc": "KEY_ESC",
    "escape": "KEY_ESC",
    "tab": "KEY_TAB",
    "backspace": "KEY_BACKSPACE",
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
}

ALL_LOGICAL_KEYS = sorted(LOGICAL_TO_CODE.keys()) + [
    "scroll_up",
    "scroll_down",
    "scroll_click",
]
