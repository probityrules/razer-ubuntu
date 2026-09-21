"""Canonical CLI ↔ GUI feature registry for parity tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    cli: str
    action: str
    gui_page: str
    gui_handler: str


# Every CLI command path must appear here. Parity tests fail if argparse and this
# map diverge, or if the named action / GUI handler is missing.
FEATURE_MAP: tuple[Feature, ...] = (
    Feature("diagnose", "run_diagnose", "diagnose", "run_diagnose"),
    Feature("daemon", "run_daemon_foreground", "daemon", "start_daemon"),
    Feature("set-effect", "set_effect", "lighting", "apply_effect"),
    Feature("set-brightness", "set_brightness", "lighting", "apply_brightness"),
    Feature("profile.list", "list_profiles", "profiles", "refresh_profiles"),
    Feature("profile.show", "show_profile", "profiles", "show_profile"),
    Feature("profile.use", "use_profile", "profiles", "activate_profile"),
    Feature("profile.path", "profiles_path", "profiles", "open_profiles_dir"),
    Feature("info", "device_info", "device", "refresh_device"),
    Feature("gui", "launch_gui", "app", "launch"),
)

# Extra GUI-only handlers that must exist for full CLI-equivalent coverage
GUI_EXTRA_HANDLERS: tuple[tuple[str, str], ...] = (
    ("daemon", "stop_daemon"),
    ("daemon", "daemon_status"),
    ("bindings", "load_bindings"),
    ("bindings", "save_bindings"),
    ("bindings", "set_hypershift_key"),
    ("diagnose", "copy_report"),
    ("diagnose", "save_report"),
    ("lighting", "list_effects"),
)


def cli_ids() -> set[str]:
    return {f.cli for f in FEATURE_MAP}


def collect_argparse_commands(parser) -> set[str]:
    """Walk argparse subparsers and return dotted command ids."""
    found: set[str] = set()
    sub = None
    for action in parser._actions:  # noqa: SLF001
        if getattr(action, "dest", None) == "command" and hasattr(action, "choices"):
            sub = action.choices
            break
    if not sub:
        return found
    for name, subparser in sub.items():
        nested = None
        for action in subparser._actions:  # noqa: SLF001
            if action.dest and action.dest.endswith("_cmd") and hasattr(action, "choices"):
                nested = action.choices
                break
        if nested:
            for nested_name in nested:
                found.add(f"{name}.{nested_name}")
        else:
            found.add(name)
    return found
