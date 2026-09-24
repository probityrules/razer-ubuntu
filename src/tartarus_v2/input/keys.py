"""Physical key table for Tartarus V2 (Linux EV_KEY codes the device emits)."""

from __future__ import annotations

from typing import Any

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
    # Bottom keypad row is Synapse 16–19 only. Key 20 is the thumb key
    # (hyperesponse / spacebar), not a fifth key on that row.
    "key_16": 29,   # KEY_LEFTCTRL
    "key_17": 125,  # KEY_LEFTMETA (Super)
    "key_18": 100,  # KEY_RIGHTALT
    "key_19": 127,  # KEY_COMPOSE
    "key_20": 57,   # KEY_SPACE — Synapse key 20 / hyperesponse thumb
    "mode": 56,     # KEY_LEFTALT / MODE_SWITCH
    "stick_up": 103,
    "stick_left": 105,
    "stick_right": 106,
    "stick_down": 108,
}

CODE_TO_LOGICAL: dict[int, str] = {v: k for k, v in LOGICAL_TO_CODE.items()}

# Older profiles and hypershift settings used ``thumb`` as a second id for key 20.
LOGICAL_ALIASES: dict[str, str] = {
    "thumb": "key_20",
}

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

# Top-down layout matching Synapse-style numbering:
#   01–05 / 06–10 / 11–15 / 16–19   (bottom keypad row is four keys)
#   scr up, scr, scr down
#   mode, lf, up, rt, dn, key 20 (thumb — not part of the keypad row)
KEYMAP_LAYOUT: list[list[str | None]] = [
    ["key_01", "key_02", "key_03", "key_04", "key_05"],
    ["key_06", "key_07", "key_08", "key_09", "key_10"],
    ["key_11", "key_12", "key_13", "key_14", "key_15"],
    ["key_16", "key_17", "key_18", "key_19"],
    ["scroll_up", "scroll_click", "scroll_down", None, None],
    ["mode", "stick_left", "stick_up", "stick_right", "stick_down", "key_20"],
]

KEYMAP_ASCII = """
Tartarus V2 logical key map (for bindings / profile JSON)
=========================================================

  [01] [02] [03] [04] [05]
  [06] [07] [08] [09] [10]
  [11] [12] [13] [14] [15]
  [16] [17] [18] [19]
  [Scr↑] [Scr•] [Scr↓]
  [mode] [←] [↑] [→] [↓] [20]

Notes:
  - mode is often used as Hypershift (hold for secondary layer)
  - key 20 is the hyperesponse thumb key (default Space), not a fifth keypad key
  - the bottom keypad row is keys 16–19 only
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
        "key_20": "20",
    }
    if logical in aliases:
        return aliases[logical]
    if logical.startswith("key_"):
        return logical.replace("key_", "")
    return logical


def canonical_logical(name: str) -> str:
    """Map legacy ids onto the current logical name (``thumb`` → ``key_20``)."""
    return LOGICAL_ALIASES.get(name, name)


def describe_logical(logical: str) -> str:
    """Human label for editors and tooltips."""
    name = canonical_logical(logical)
    if name == "key_20":
        return "key 20 (thumb)"
    return name


def lookup_binding(bindings: dict[str, Any], logical: str) -> Any | None:
    """Read a binding, treating the legacy ``thumb`` id as key 20.

    When both names are present, ``thumb`` wins: that entry was wired to the
    physical spacebar, while the old ``key_20`` entry was a phantom keypad key.
    """
    if not isinstance(bindings, dict):
        return None
    canon = canonical_logical(logical)
    if canon == "key_20" and "thumb" in bindings:
        return bindings["thumb"]
    if canon in bindings:
        return bindings[canon]
    return None


def fold_thumb_alias(profile: dict[str, Any]) -> dict[str, Any]:
    """Store key 20 once. The legacy ``thumb`` name is not a separate key."""
    hs = profile.get("hypershift_key")
    if isinstance(hs, str):
        profile["hypershift_key"] = canonical_logical(hs)
    for layer_name in ("standard", "hypershift"):
        layer = profile.get(layer_name)
        if not isinstance(layer, dict):
            continue
        bindings = layer.get("bindings")
        if not isinstance(bindings, dict):
            continue
        if "thumb" in bindings:
            bindings["key_20"] = bindings.pop("thumb")
    return profile
