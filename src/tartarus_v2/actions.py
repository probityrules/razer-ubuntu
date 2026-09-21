"""Shared actions used by CLI and GUI (mock-friendly)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tartarus_v2 import profiles as prof

LIGHTING_EFFECTS = (
    "none",
    "static",
    "spectrum",
    "wave",
    "breath",
    "reactive",
    "starlight",
)


def device_info(debug: bool = False) -> dict[str, Any]:
    from tartarus_v2.hid.chroma import ChromaController
    from tartarus_v2.hid.device import TartarusDevice

    with TartarusDevice(debug=debug) as dev:
        chroma = ChromaController(dev)
        return {
            "firmware": chroma.get_firmware(),
            "serial": chroma.get_serial(),
            "brightness": chroma.get_brightness(),
        }


def set_brightness(value: int, debug: bool = False) -> None:
    from tartarus_v2.hid.chroma import ChromaController
    from tartarus_v2.hid.device import TartarusDevice

    with TartarusDevice(debug=debug) as dev:
        ChromaController(dev).set_brightness(int(value))


def set_effect(
    effect: str,
    *,
    rgb: str = "00FF00",
    rgb2: str | None = None,
    direction: int = 1,
    speed: int = 2,
    brightness: int | None = None,
    debug: bool = False,
) -> None:
    if effect not in LIGHTING_EFFECTS:
        raise ValueError(f"Unknown effect: {effect}")

    from tartarus_v2.hid.chroma import ChromaController
    from tartarus_v2.hid.device import TartarusDevice

    with TartarusDevice(debug=debug) as dev:
        chroma = ChromaController(dev)
        if brightness is not None:
            chroma.set_brightness(int(brightness))
        if effect == "none":
            chroma.set_effect_none()
        elif effect == "static":
            chroma.set_effect_static(rgb)
        elif effect == "spectrum":
            chroma.set_effect_spectrum()
        elif effect == "wave":
            chroma.set_effect_wave(direction)
        elif effect == "breath":
            chroma.set_effect_breath(rgb, rgb2)
        elif effect == "reactive":
            chroma.set_effect_reactive(rgb, speed)
        elif effect == "starlight":
            chroma.set_effect_starlight(rgb, speed)


def list_profiles() -> list[dict[str, Any]]:
    active = prof.get_active_profile_name()
    return [{"name": n, "active": n == active} for n in prof.list_profiles()]


def show_profile(name: str | None = None) -> dict[str, Any]:
    return prof.load_profile(name or prof.get_active_profile_name())


def use_profile(name: str) -> str:
    prof.load_profile(name)
    prof.set_active_profile_name(name)
    return name


def profiles_path() -> Path:
    return prof.profiles_dir()


def save_profile_data(profile: dict[str, Any], name: str | None = None) -> Path:
    return prof.save_profile(profile, name)


def set_hypershift_key(profile_name: str, key: str) -> dict[str, Any]:
    data = prof.load_profile(profile_name)
    data["hypershift_key"] = key
    prof.save_profile(data, profile_name)
    return data


def save_bindings(
    profile_name: str,
    layer: str,
    bindings: dict[str, Any],
    hypershift_key: str | None = None,
) -> dict[str, Any]:
    if layer not in ("standard", "hypershift"):
        raise ValueError("layer must be standard or hypershift")
    data = prof.load_profile(profile_name)
    data.setdefault(layer, {})["bindings"] = bindings
    if hypershift_key is not None:
        data["hypershift_key"] = hypershift_key
    prof.save_profile(data, profile_name)
    return data


def duplicate_profile(source: str, dest: str) -> Path:
    data = prof.load_profile(source)
    data["name"] = dest
    return prof.save_profile(data, dest)


def run_diagnose(
    *,
    out: str | None = None,
    listen: float = 0,
    skip_probe: bool = False,
    print_report: bool = True,
) -> str:
    from tartarus_v2.diagnose import build_report

    report = build_report(listen_seconds=float(listen or 0), skip_probe=bool(skip_probe))
    if print_report:
        print(report)
    if out:
        path = Path(out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        if print_report:
            print(f"\nWrote {path}", flush=True)
    return report


def run_daemon_foreground(profile: str | None = None, debug: bool = False) -> None:
    from tartarus_v2.daemon import Daemon

    Daemon(profile_name=profile, debug=debug).start()


def launch_gui(debug: bool = False) -> int:
    from tartarus_v2.gui.app import run_gui

    return run_gui(debug=debug)


def format_profile_json(profile: dict[str, Any]) -> str:
    return json.dumps(profile, indent=2)
