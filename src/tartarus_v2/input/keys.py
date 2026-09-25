"""Physical key table for Tartarus V2 (Linux EV_KEY codes the device emits)."""

from __future__ import annotations

from typing import Any

# Logical name -> Linux EV_KEY code emitted by the firmware/HID stack.
# Calibrated from live `evtest` on Tartarus V2 (physical keypad → code).
LOGICAL_TO_CODE: dict[str, int] = {
    "key_01": 2,    # KEY_1
    "key_02": 3,    # KEY_2
    "key_03": 4,    # KEY_3
    "key_04": 5,    # KEY_4
    "key_05": 6,    # KEY_5
    "key_06": 15,   # KEY_TAB
    "key_07": 16,   # KEY_Q
    "key_08": 17,   # KEY_W
    "key_09": 18,   # KEY_E
    "key_10": 19,   # KEY_R
    "key_11": 58,   # KEY_CAPSLOCK
    "key_12": 30,   # KEY_A
    "key_13": 31,   # KEY_S
    "key_14": 32,   # KEY_D
    "key_15": 33,   # KEY_F
    # Bottom keypad row is Synapse 16–19 only. Key 20 is the thumb key
    # (hyperesponse / spacebar), not a fifth key on that row.
    "key_16": 42,   # KEY_LEFTSHIFT
    "key_17": 44,   # KEY_Z
    "key_18": 45,   # KEY_X
    "key_19": 46,   # KEY_C
    "key_20": 57,   # KEY_SPACE — Synapse key 20 / hyperesponse thumb
    "mode": 56,     # KEY_LEFTALT / MODE_SWITCH
    "stick_up": 103,     # KEY_UP
    "stick_left": 105,   # KEY_LEFT
    "stick_right": 106,  # KEY_RIGHT
    "stick_down": 108,   # KEY_DOWN
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

# Device-like Bindings layout (wireframe):
#   keypad 01–19 | tall scroll capsule | mode / stick circle / 20
#
#   [01] [02] [03] [04] [05]      ╔══╗   (mode)
#   [06] [07] [08] [09] [10]      ║Scr║    ┌ stick ┐
#   [11] [12] [13] [14] [15]      ║whl║    │  ↑←→↓ │
#   [16] [17] [18] [19]           ╚══╝    └───────┘
#                                            [20]
KEYMAP_PAD_LAYOUT: list[list[str | None]] = [
    ["key_01", "key_02", "key_03", "key_04", "key_05"],
    ["key_06", "key_07", "key_08", "key_09", "key_10"],
    ["key_11", "key_12", "key_13", "key_14", "key_15"],
    ["key_16", "key_17", "key_18", "key_19"],
]
KEYMAP_SCROLL_COLUMN: list[str] = ["scroll_up", "scroll_click", "scroll_down"]

# Flat row list kept for tests / callers that iterate every logical key.
KEYMAP_LAYOUT: list[list[str | None]] = [
    *KEYMAP_PAD_LAYOUT,
    ["scroll_up", "scroll_click", "scroll_down"],
    ["mode", "stick_left", "stick_up", "stick_right", "stick_down", "key_20"],
]

KEYMAP_ASCII = """
Tartarus V2 logical key map (for bindings / profile JSON)
=========================================================

  [01] [02] [03] [04] [05]      ╔══╗   (mode)
  [06] [07] [08] [09] [10]      ║Scr║    ┌ stick ┐
  [11] [12] [13] [14] [15]      ║whl║    │  ↑←→↓ │
  [16] [17] [18] [19]           ╚══╝    └───────┘
                                           [20]

Notes:
  - mode is often used as Hypershift (hold for secondary layer)
  - key 20 is the hyperesponse thumb key (default Space), not a fifth keypad key
  - the bottom keypad row is keys 16–19 only
  - scroll is one tall capsule (↑ / click / ↓ hit zones)
  - stick directions share one circular cluster
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


def strip_hypershift_key_bindings(
    bindings: dict[str, Any],
    hypershift_key: str | None,
) -> dict[str, Any]:
    """Return a copy of bindings with the Hypershift modifier key removed."""
    out = dict(bindings or {})
    if not hypershift_key:
        return out
    canon = canonical_logical(hypershift_key)
    out.pop(canon, None)
    if canon == "key_20":
        out.pop("thumb", None)
    elif hypershift_key != canon:
        out.pop(hypershift_key, None)
    return out


# Special action tokens the remapper handles as dict bindings (not KEY_* names).
BINDING_ACTION_TOKENS: dict[str, dict[str, str]] = {
    "profile_next": {"type": "profile_next"},
    "profile_prev": {"type": "profile_prev"},
}

# Physical scroll-wheel logical keys (input side).
SCROLL_LOGICAL_KEYS = frozenset({"scroll_up", "scroll_down", "scroll_click"})

# Output tokens that emit mouse-wheel relative events (not KEY_*).
# Values are (REL code name, signed ticks) resolved against evdev.ecodes.
WHEEL_OUTPUT_TOKENS: dict[str, tuple[str, int]] = {
    "scroll_up": ("REL_WHEEL", 1),
    "scroll_down": ("REL_WHEEL", -1),
    "wheel_up": ("REL_WHEEL", 1),
    "wheel_down": ("REL_WHEEL", -1),
    "scroll_left": ("REL_HWHEEL", -1),
    "scroll_right": ("REL_HWHEEL", 1),
    "wheel_left": ("REL_HWHEEL", -1),
    "wheel_right": ("REL_HWHEEL", 1),
}


def binding_source_kind(logical: str | None) -> str:
    """Picker/validation kind for a physical key: ``scroll`` or ``key``."""
    if not logical:
        return "key"
    name = canonical_logical(logical)
    if name in SCROLL_LOGICAL_KEYS or logical in SCROLL_LOGICAL_KEYS:
        return "scroll"
    return "key"


def format_binding_for_entry(value: Any) -> str:
    """Flatten a profile binding value into editable entry text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        kind = value.get("type", "key")
        if kind in BINDING_ACTION_TOKENS:
            return str(kind)
        if kind == "wheel":
            return str(value.get("dir") or value.get("key") or "scroll_up")
        if kind == "macro":
            steps = value.get("steps") or []
            if steps and isinstance(steps[0], dict):
                return str(steps[0].get("tap") or "")
            return "macro"
        if kind == "key":
            return str(value.get("key") or value.get("keys") or "")
        return str(kind)
    return str(value)


def parse_binding_from_entry(text: str) -> Any | None:
    """Parse entry text into a profile binding value.

    Empty → ``None`` (clear). ``profile_next`` / ``profile_prev`` → action
    dicts. Wheel tokens stay as strings (remapper emits REL_*). Everything
    else stays a string (letters, aliases, ``ctrl+c`` chords).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    if lower in BINDING_ACTION_TOKENS:
        return dict(BINDING_ACTION_TOKENS[lower])
    if lower in WHEEL_OUTPUT_TOKENS:
        return lower
    return cleaned


def _token_parts(text: str) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if "+" in cleaned and not cleaned.upper().startswith("KEY_"):
        return [p.strip() for p in cleaned.split("+") if p.strip()]
    return [cleaned]


def validate_binding_text(text: str, *, source_kind: str = "key") -> str | None:
    """Return an error message if ``text`` is not valid for this source kind.

    Empty text is always valid (clears the binding).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    if lower in BINDING_ACTION_TOKENS:
        return None

    parts = _token_parts(cleaned)
    if source_kind == "scroll":
        # Scroll physical keys: actions, wheel emits, or normal key tokens.
        for part in parts:
            pl = part.lower()
            if pl in BINDING_ACTION_TOKENS or pl in WHEEL_OUTPUT_TOKENS:
                continue
            if pl in OUTPUT_ALIASES:
                continue
            if len(pl) == 1 and pl.isalnum():
                continue
            if pl.startswith("f") and pl[1:].isdigit() and 1 <= int(pl[1:]) <= 24:
                continue
            if pl.startswith("key_") or pl.startswith("btn_"):
                continue
            # Allow common words the remapper maps to KEY_*
            if pl.isalpha() or pl.isalnum():
                continue
            return (
                f"Unknown binding {part!r}. Use Insert… or a key name "
                "(e.g. space, ctrl+c, scroll_up)."
            )
        return None

    # Keyboard / stick keys: never allow wheel-only tokens (they are not KEY_*).
    for part in parts:
        pl = part.lower()
        if pl in WHEEL_OUTPUT_TOKENS:
            return (
                f"{part!r} is a mouse-wheel output — bind it on the scroll "
                "wheel keys, or pick a keyboard key from Insert…"
            )
        if pl in BINDING_ACTION_TOKENS:
            continue
        if pl in OUTPUT_ALIASES:
            continue
        if len(pl) == 1 and pl.isalnum():
            continue
        if pl.startswith("f") and pl[1:].isdigit() and 1 <= int(pl[1:]) <= 24:
            continue
        if pl.isalpha() or pl.isalnum() or pl.startswith("key_") or pl.startswith("btn_"):
            continue
        return f"Unknown binding {part!r}. Use Insert… or a key/chord name."
    return None


def binding_picker_choices(*, kind: str = "key") -> list[tuple[str, str | None]]:
    """Labels and values for the Bindings Insert dropdown.

    ``kind`` is ``scroll`` (physical wheel) or ``key`` (pad / stick / thumb).
    First row is a no-op placeholder (``None``). ``\"\"`` clears the binding.
    """
    items: list[tuple[str, str | None]] = [
        ("Insert…", None),
        ("Clear binding", ""),
        ("Profile next", "profile_next"),
        ("Profile previous", "profile_prev"),
    ]

    if kind == "scroll":
        items.extend(
            [
                ("Mouse wheel up", "scroll_up"),
                ("Mouse wheel down", "scroll_down"),
                ("Mouse wheel left", "scroll_left"),
                ("Mouse wheel right", "scroll_right"),
            ]
        )
        for name in (
            "space",
            "enter",
            "tab",
            "esc",
            "backspace",
            "ctrl",
            "shift",
            "alt",
            "super",
        ):
            items.append((name, name))
        return items

    modifiers = (
        "ctrl",
        "shift",
        "alt",
        "super",
        "rctrl",
        "rshift",
        "ralt",
        "tab",
        "esc",
        "enter",
        "space",
        "backspace",
        "up",
        "down",
        "left",
        "right",
    )
    for name in modifiers:
        items.append((name, name))

    for ch in "abcdefghijklmnopqrstuvwxyz":
        items.append((ch, ch))
    for ch in "0123456789":
        items.append((ch, ch))
    for n in range(1, 25):
        items.append((f"F{n}", f"F{n}"))

    chords = (
        "ctrl+c",
        "ctrl+v",
        "ctrl+x",
        "ctrl+z",
        "ctrl+a",
        "ctrl+s",
        "ctrl+f",
        "alt+tab",
        "ctrl+shift+esc",
        "super+tab",
    )
    for chord in chords:
        items.append((chord, chord))

    media = (
        "mute",
        "volumeup",
        "volumedown",
        "playpause",
        "nextsong",
        "previoussong",
    )
    for name in media:
        items.append((name, name))

    return items
