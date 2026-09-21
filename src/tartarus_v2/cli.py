"""CLI entrypoint for tartarus-v2."""

from __future__ import annotations

import argparse
import sys

from tartarus_v2 import __version__
from tartarus_v2 import actions
from tartarus_v2.logging_util import setup_logging


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--debug", action="store_true", help="Verbose HID/remap logging")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tartarus-v2",
        description="Standalone userspace driver for Razer Tartarus V2 (Ubuntu/Linux)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_diag = sub.add_parser("diagnose", help="Paste-ready system dump for remote debugging")
    _add_common(p_diag)
    p_diag.add_argument("--out", help="Also write the report to this file")
    p_diag.add_argument("--listen", type=float, default=0, help="Seconds to capture key events")
    p_diag.add_argument("--skip-probe", action="store_true", help="Skip live USB chroma probe")

    p_daemon = sub.add_parser("daemon", help="Run lighting + remapper daemon (foreground)")
    _add_common(p_daemon)
    p_daemon.add_argument("--profile", default=None, help="Profile name to load")

    p_effect = sub.add_parser("set-effect", help="Set a lighting effect")
    _add_common(p_effect)
    p_effect.add_argument("effect", choices=list(actions.LIGHTING_EFFECTS))
    p_effect.add_argument("--rgb", default="00FF00")
    p_effect.add_argument("--rgb2", default=None)
    p_effect.add_argument("--direction", type=int, default=1)
    p_effect.add_argument("--speed", type=int, default=2)
    p_effect.add_argument("--brightness", type=int, default=None)

    p_bright = sub.add_parser("set-brightness", help="Set brightness 0-255")
    _add_common(p_bright)
    p_bright.add_argument("value", type=int)

    p_prof = sub.add_parser("profile", help="Manage profiles")
    _add_common(p_prof)
    p_prof_sub = p_prof.add_subparsers(dest="profile_cmd", required=True)
    p_prof_sub.add_parser("list", help="List profiles")
    p_show = p_prof_sub.add_parser("show", help="Show a profile JSON")
    p_show.add_argument("name", nargs="?", default=None)
    p_use = p_prof_sub.add_parser("use", help="Set active profile")
    p_use.add_argument("name")
    p_prof_sub.add_parser("path", help="Print profiles directory")

    p_info = sub.add_parser("info", help="Print firmware/serial/brightness")
    _add_common(p_info)

    p_gui = sub.add_parser("gui", help="Open the GTK4 / Libadwaita control app")
    _add_common(p_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(debug=bool(getattr(args, "debug", False)))

    if args.command == "diagnose":
        actions.run_diagnose(
            out=args.out,
            listen=args.listen,
            skip_probe=args.skip_probe,
            print_report=True,
        )
        return 0

    if args.command == "daemon":
        actions.run_daemon_foreground(profile=args.profile, debug=args.debug)
        return 0

    if args.command == "set-effect":
        actions.set_effect(
            args.effect,
            rgb=args.rgb,
            rgb2=args.rgb2,
            direction=args.direction,
            speed=args.speed,
            brightness=args.brightness,
            debug=args.debug,
        )
        return 0

    if args.command == "set-brightness":
        actions.set_brightness(args.value, debug=args.debug)
        return 0

    if args.command == "profile":
        if args.profile_cmd == "list":
            for item in actions.list_profiles():
                mark = "*" if item["active"] else " "
                print(f"{mark} {item['name']}")
            return 0
        if args.profile_cmd == "show":
            print(actions.format_profile_json(actions.show_profile(args.name)))
            return 0
        if args.profile_cmd == "use":
            name = actions.use_profile(args.name)
            print(f"Active profile set to {name}")
            return 0
        if args.profile_cmd == "path":
            print(actions.profiles_path())
            return 0

    if args.command == "info":
        info = actions.device_info(debug=args.debug)
        print(f"firmware: {info['firmware']}")
        print(f"serial:   {info['serial']}")
        print(f"brightness: {info['brightness']}")
        return 0

    if args.command == "gui":
        return actions.launch_gui(debug=args.debug)

    parser.error(f"Unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
