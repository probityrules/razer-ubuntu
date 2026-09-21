"""GUI page controllers (no GI dependency — fully unit-testable)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from tartarus_v2 import actions
from tartarus_v2 import daemon_control
from tartarus_v2.actions import LIGHTING_EFFECTS
from tartarus_v2.input.keys import ALL_LOGICAL_KEYS


class DeviceController:
    def refresh_device(self, debug: bool = False) -> dict[str, Any]:
        return actions.device_info(debug=debug)


class LightingController:
    def list_effects(self) -> tuple[str, ...]:
        return LIGHTING_EFFECTS

    def apply_effect(
        self,
        effect: str,
        *,
        rgb: str = "00FF00",
        rgb2: str | None = None,
        direction: int = 1,
        speed: int = 2,
        brightness: int | None = None,
        debug: bool = False,
        save_to_profile: bool = False,
        profile_name: str | None = None,
    ) -> None:
        actions.set_effect(
            effect,
            rgb=rgb,
            rgb2=rgb2,
            direction=direction,
            speed=speed,
            brightness=brightness,
            debug=debug,
        )
        if save_to_profile:
            name = profile_name or actions.show_profile()["name"]
            data = actions.show_profile(name)
            lighting = {
                "effect": effect,
                "rgb": rgb,
                "direction": direction,
                "speed": speed,
            }
            if brightness is not None:
                lighting["brightness"] = brightness
            if rgb2:
                lighting["rgb2"] = rgb2
            data["lighting"] = lighting
            actions.save_profile_data(data, name)

    def apply_brightness(self, value: int, debug: bool = False) -> None:
        actions.set_brightness(value, debug=debug)


class ProfilesController:
    def refresh_profiles(self) -> list[dict[str, Any]]:
        return actions.list_profiles()

    def show_profile(self, name: str | None = None) -> dict[str, Any]:
        return actions.show_profile(name)

    def activate_profile(self, name: str) -> str:
        return actions.use_profile(name)

    def open_profiles_dir(self) -> Path:
        return actions.profiles_path()

    def duplicate_profile(self, source: str, dest: str) -> Path:
        return actions.duplicate_profile(source, dest)


class BindingsController:
    def logical_keys(self) -> list[str]:
        return list(ALL_LOGICAL_KEYS)

    def load_bindings(self, profile_name: str | None = None) -> dict[str, Any]:
        return actions.show_profile(profile_name)

    def save_bindings(
        self,
        profile_name: str,
        layer: str,
        bindings: dict[str, Any],
        hypershift_key: str | None = None,
    ) -> dict[str, Any]:
        return actions.save_bindings(profile_name, layer, bindings, hypershift_key)

    def set_hypershift_key(self, profile_name: str, key: str) -> dict[str, Any]:
        return actions.set_hypershift_key(profile_name, key)


class DaemonController:
    def start_daemon(self, profile: str | None = None, debug: bool = False) -> daemon_control.DaemonStatus:
        return daemon_control.start(profile=profile, debug=debug)

    def stop_daemon(self) -> daemon_control.DaemonStatus:
        return daemon_control.stop()

    def daemon_status(self) -> daemon_control.DaemonStatus:
        return daemon_control.status()


class DiagnoseController:
    def __init__(self) -> None:
        self.last_report: str = ""

    def run_diagnose(
        self,
        *,
        out: str | None = None,
        listen: float = 0,
        skip_probe: bool = False,
    ) -> str:
        self.last_report = actions.run_diagnose(
            out=out,
            listen=listen,
            skip_probe=skip_probe,
            print_report=False,
        )
        return self.last_report

    def copy_report(self) -> str:
        return self.last_report

    def save_report(self, path: str | Path) -> Path:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.last_report or "", encoding="utf-8")
        return target


class AppController:
    def launch(self, debug: bool = False) -> int:
        return actions.launch_gui(debug=debug)


PAGE_CONTROLLERS: dict[str, type] = {
    "device": DeviceController,
    "lighting": LightingController,
    "profiles": ProfilesController,
    "bindings": BindingsController,
    "daemon": DaemonController,
    "diagnose": DiagnoseController,
    "app": AppController,
}


def get_handler(page: str, handler: str) -> Callable[..., Any]:
    cls = PAGE_CONTROLLERS[page]
    method = getattr(cls, handler, None)
    if method is None:
        raise AttributeError(f"{cls.__name__} has no handler {handler!r}")
    return method
