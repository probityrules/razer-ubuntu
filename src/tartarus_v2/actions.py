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
    nudge_daemon_reload()
    return name


def profiles_path() -> Path:
    return prof.profiles_dir()


def save_profile_data(profile: dict[str, Any], name: str | None = None) -> Path:
    path = prof.save_profile(profile, name)
    saved = name or profile.get("name")
    if saved and saved == prof.get_active_profile_name():
        nudge_daemon_reload()
    return path


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


def nudge_daemon_reload() -> str:
    """If the remap daemon is running, ask it to re-read the active profile."""
    from tartarus_v2 import daemon_control

    st = daemon_control.reload()
    return st.detail


def apply_active_profile() -> str:
    """Reload the running daemon so pending binding/profile edits take effect."""
    return nudge_daemon_reload()


def duplicate_profile(source: str, dest: str) -> Path:
    data = prof.load_profile(source)
    data["name"] = dest
    return prof.save_profile(data, dest)


def create_profile(name: str, *, clone_active: bool = True) -> Path:
    """Create a new profile from the active one (or the built-in default)."""
    name = name.strip()
    if not name:
        raise ValueError("Profile name required")
    if any(p["name"] == name for p in list_profiles()):
        raise ValueError(f"Profile already exists: {name}")
    if clone_active:
        data = dict(prof.load_profile(prof.get_active_profile_name()))
    else:
        data = prof.default_profile()
    data["name"] = name
    return prof.save_profile(data, name)


def is_autostart_enabled() -> bool:
    from tartarus_v2.autostart import is_autostart_enabled as _enabled

    return _enabled()


def set_autostart_enabled(enabled: bool) -> Path:
    from tartarus_v2.autostart import set_autostart_enabled as _set

    return _set(enabled)


def start_daemon_background(profile: str | None = None, debug: bool = False) -> Any:
    from tartarus_v2 import daemon_control

    return daemon_control.start(profile=profile, debug=debug)


def uninstall_package(*, noninteractive: bool = False) -> str:
    """Remove the tartarus-v2 .deb via pkexec/apt when available."""
    import shutil
    import subprocess

    from tartarus_v2 import daemon_control

    try:
        daemon_control.stop()
    except Exception:  # noqa: BLE001
        pass

    if not shutil.which("apt-get"):
        return (
            "apt-get not found. Uninstall manually, e.g. remove the package "
            "or delete the install directory."
        )

    cmd = ["apt-get", "remove", "-y", "tartarus-v2"]
    if shutil.which("pkexec"):
        cmd = ["pkexec", *cmd]
    elif not noninteractive:
        return "pkexec not found; run: sudo apt-get remove -y tartarus-v2"

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return f"Uninstall failed: {exc}"

    if proc.returncode == 0:
        return "tartarus-v2 removed"
    err = (proc.stderr or proc.stdout or "").strip()
    return f"Uninstall failed (code {proc.returncode}): {err[:500]}"


def permission_status() -> Any:
    from tartarus_v2.permissions import permission_status as _status

    return _status()


def fix_permissions() -> str:
    from tartarus_v2.permissions import fix_permissions as _fix

    return _fix()


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
