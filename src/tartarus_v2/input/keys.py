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
    # Bottom keypad row (Synapse 16–19). key_20 is shown as the thumb key in the UI.
    "key_16": 29,   # KEY_LEFTCTRL
    "key_17": 125,  # KEY_LEFTMETA (Super)
    "key_18": 100,  # KEY_RIGHTALT
    "key_19": 127,  # KEY_COMPOSE
    "key_20": 54,   # KEY_RIGHTSHIFT (also editable via combo; pad shows thumb as 20)
    "mode": 56,     # KEY_LEFTALT / MODE_SWITCH
    "thumb": 57,    # KEY_SPACE — Synapse "20" / thumb
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

# Top-down layout matching Synapse-style numbering the user expects:
#   01–05 / 06–10 / 11–15 / 16–19
#   scr up, scr, scr down
#   mode, lf, up, rt, dn, thumb(20)
KEYMAP_LAYOUT: list[list[str | None]] = [
    ["key_01", "key_02", "key_03", "key_04", "key_05"],
    ["key_06", "key_07", "key_08", "key_09", "key_10"],
    ["key_11", "key_12", "key_13", "key_14", "key_15"],
    ["key_16", "key_17", "key_18", "key_19", None],
    ["scroll_up", "scroll_click", "scroll_down", None, None],
    ["mode", "stick_left", "stick_up", "stick_right", "stick_down", "thumb"],
]

KEYMAP_ASCII = """
Tartarus V2 logical key map (for bindings / profile JSON)
=========================================================

  [01] [02] [03] [04] [05]
  [06] [07] [08] [09] [10]
  [11] [12] [13] [14] [15]
  [16] [17] [18] [19]
  [Scr↑] [Scr•] [Scr↓]
  [mode] [←] [↑] [→] [↓] [20/thumb]

Notes:
  - mode is often used as Hypershift (hold for secondary layer)
  - thumb is labeled 20 (hyperesponse thumb key; default Space)
  - key_20 remains a valid binding id in profiles / combo lists
""".strip()


def short_label(logical: str) -> str:
    """Compact label for keymap buttons."""
    aliases = {
        "stick_up": "↑",
        "stick_down": "↓",
        "stick_left": "←",
        "stick_right": "→",
        "scroll_up": "Scr↑",
        "scroll_down": "Scr↓",
        "scroll_click": "Scr•",
        "mode": "mode",
        "thumb": "20",
    }
    if logical in aliases:
        return aliases[logical]
    if logical.startswith("key_"):
        return logical.replace("key_", "")
    return logical
