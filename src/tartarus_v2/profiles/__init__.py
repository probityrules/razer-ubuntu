"""Profile load/save helpers."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

from tartarus_v2.constants import DEFAULT_PROFILE_NAME
from tartarus_v2.logging_util import cache_dir


def package_configs_dir() -> Path:
    # repo configs/ when editable; fall back beside package
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "configs",  # src/tartarus_v2/profiles -> repo/configs
        here.parents[2] / "configs",
        Path.cwd() / "configs",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def profiles_dir() -> Path:
    path = cache_dir() / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_default_profile() -> Path:
    dest = profiles_dir() / f"{DEFAULT_PROFILE_NAME}.json"
    if dest.exists():
        return dest
    src = package_configs_dir() / "default.json"
    if src.exists():
        shutil.copy2(src, dest)
    else:
        dest.write_text(json.dumps(default_profile(), indent=2) + "\n", encoding="utf-8")
    return dest


def default_profile() -> dict[str, Any]:
    return {
        "name": "default",
        "hypershift_key": "mode",
        "lighting": {
            "effect": "spectrum",
            "brightness": 128,
        },
        "standard": {
            "bindings": {
                "key_01": "1",
                "key_02": "2",
                "key_03": "3",
                "key_04": "4",
                "key_05": "5",
                "key_06": "q",
                "key_07": "w",
                "key_08": "e",
                "key_09": "r",
                "key_10": "t",
                "key_11": "a",
                "key_12": "s",
                "key_13": "d",
                "key_14": "f",
                "key_15": "g",
                "key_16": "ctrl",
                "key_17": "super",
                "key_18": "alt",
                "key_19": "b",
                "key_20": "n",
                "thumb": "space",
                "stick_up": "up",
                "stick_down": "down",
                "stick_left": "left",
                "stick_right": "right",
                "scroll_up": {"type": "profile_next"},
                "scroll_down": {"type": "profile_prev"},
            }
        },
        "hypershift": {
            "bindings": {
                "key_01": "F1",
                "key_02": "F2",
                "key_03": "F3",
                "key_04": "F4",
                "key_05": "F5",
                "key_06": "F6",
                "key_07": "F7",
                "key_08": "F8",
                "key_09": "F9",
                "key_10": "F10",
                "key_11": "F11",
                "key_12": "F12",
                "key_13": "escape",
                "key_14": {"type": "macro", "steps": [
                    {"tap": "ctrl+c"},
                    {"delay_ms": 30},
                ]},
                "key_15": {"type": "macro", "steps": [{"tap": "ctrl+v"}]},
                "key_16": "F13",
                "key_17": "F14",
                "key_18": "F15",
                "key_19": "F16",
                "key_20": "F17",
                "thumb": "enter",
                "stick_up": "pageup",
                "stick_down": "pagedown",
                "stick_left": "home",
                "stick_right": "end",
            }
        },
    }


def list_profiles() -> list[str]:
    ensure_default_profile()
    names = []
    for p in sorted(profiles_dir().glob("*.json")):
        names.append(p.stem)
    return names


def load_profile(name: str = DEFAULT_PROFILE_NAME) -> dict[str, Any]:
    ensure_default_profile()
    path = profiles_dir() / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {name} ({path})")
    data = json.loads(path.read_text(encoding="utf-8"))
    # Filename stem is the source of truth — never trust a stale embedded "name".
    data["name"] = name
    data.setdefault("hypershift_key", "mode")
    data.setdefault("standard", {"bindings": {}})
    data.setdefault("hypershift", {"bindings": {}})
    data.setdefault("lighting", {"effect": "spectrum", "brightness": 128})
    return data


def save_profile(profile: dict[str, Any], name: str | None = None) -> Path:
    name = name or profile.get("name") or DEFAULT_PROFILE_NAME
    # Deep-copy so callers cannot accidentally share nested bindings across profiles.
    profile = copy.deepcopy(profile)
    profile["name"] = name
    path = profiles_dir() / f"{name}.json"
    path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return path


def active_profile_path() -> Path:
    return cache_dir() / "active_profile"


def get_active_profile_name() -> str:
    path = active_profile_path()
    if path.exists():
        return path.read_text(encoding="utf-8").strip() or DEFAULT_PROFILE_NAME
    return DEFAULT_PROFILE_NAME


def set_active_profile_name(name: str) -> None:
    active_profile_path().write_text(name.strip() + "\n", encoding="utf-8")


def cycle_profile(direction: str = "next") -> str:
    names = list_profiles()
    if not names:
        ensure_default_profile()
        names = list_profiles()
    current = get_active_profile_name()
    if current not in names:
        current = names[0]
    idx = names.index(current)
    if direction == "prev":
        idx = (idx - 1) % len(names)
    else:
        idx = (idx + 1) % len(names)
    set_active_profile_name(names[idx])
    return names[idx]
