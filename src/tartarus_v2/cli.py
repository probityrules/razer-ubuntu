"""CLI entrypoint for tartarus-v2."""

from __future__ import annotations

import argparse
import json
import sys

from tartarus_v2 import __version__
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

    p_diag = sub.add_parser(
        "diagnose",
        help="Paste-ready system dump for remote debugging",
    )
    _add_common(p_diag)
    p_diag.add_argument(
        "--out",
        help="Also write the report to this file (e.g. ~/tartarus-diagnose.log)",
    )
    p_diag.add_argument(
        "--listen",
        type=float,
        default=0,
        help="Seconds to capture raw key events (0=skip)",
    )
    p_diag.add_argument(
        "--skip-probe",
        action="store_true",
        help="Skip live USB chroma probe",
    )

    p_daemon = sub.add_parser("daemon", help="Run lighting + remapper daemon")
    _add_common(p_daemon)
    p_daemon.add_argument("--profile", default=None, help="Profile name to load")

    p_effect = sub.add_parser("set-effect", help="Set a lighting effect")
    _add_common(p_effect)
    p_effect.add_argument(
        "effect",
        choices=["none", "static", "spectrum", "wave", "breath", "reactive", "starlight"],
    )
    p_effect.add_argument("--rgb", default="00FF00", help="RRGGBB for static/breath/reactive")
    p_effect.add_argument("--rgb2", default=None, help="Second colour for dual breath")
    p_effect.add_argument("--direction", type=int, default=1, help="Wave direction 0-2")
    p_effect.add_argument("--speed", type=int, default=2, help="Reactive/starlight speed")
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(debug=bool(getattr(args, "debug", False)))

    if args.command == "diagnose":
        from tartarus_v2.diagnose import run_diagnose

        return run_diagnose(args)

    if args.command == "daemon":
        from tartarus_v2.daemon import Daemon

        Daemon(profile_name=args.profile, debug=args.debug).start()
        return 0

    if args.command == "set-effect":
        from tartarus_v2.hid.chroma import ChromaController
        from tartarus_v2.hid.device import TartarusDevice

        with TartarusDevice(debug=args.debug) as dev:
            chroma = ChromaController(dev)
            if args.brightness is not None:
                chroma.set_brightness(args.brightness)
            if args.effect == "none":
                chroma.set_effect_none()
            elif args.effect == "static":
                chroma.set_effect_static(args.rgb)
            elif args.effect == "spectrum":
                chroma.set_effect_spectrum()
            elif args.effect == "wave":
                chroma.set_effect_wave(args.direction)
            elif args.effect == "breath":
                chroma.set_effect_breath(args.rgb, args.rgb2)
            elif args.effect == "reactive":
                chroma.set_effect_reactive(args.rgb, args.speed)
            elif args.effect == "starlight":
                chroma.set_effect_starlight(args.rgb, args.speed)
        return 0

    if args.command == "set-brightness":
        from tartarus_v2.hid.chroma import ChromaController
        from tartarus_v2.hid.device import TartarusDevice

        with TartarusDevice(debug=args.debug) as dev:
            ChromaController(dev).set_brightness(args.value)
        return 0

    if args.command == "profile":
        from tartarus_v2 import profiles as prof

        if args.profile_cmd == "list":
            active = prof.get_active_profile_name()
            for name in prof.list_profiles():
                mark = "*" if name == active else " "
                print(f"{mark} {name}")
            return 0
        if args.profile_cmd == "show":
            name = args.name or prof.get_active_profile_name()
            print(json.dumps(prof.load_profile(name), indent=2))
            return 0
        if args.profile_cmd == "use":
            prof.load_profile(args.name)  # validate exists
            prof.set_active_profile_name(args.name)
            print(f"Active profile set to {args.name}")
            return 0
        if args.profile_cmd == "path":
            print(prof.profiles_dir())
            return 0

    if args.command == "info":
        from tartarus_v2.hid.chroma import ChromaController
        from tartarus_v2.hid.device import TartarusDevice

        with TartarusDevice(debug=args.debug) as dev:
            chroma = ChromaController(dev)
            print(f"firmware: {chroma.get_firmware()}")
            print(f"serial:   {chroma.get_serial()}")
            print(f"brightness: {chroma.get_brightness()}")
        return 0

    parser.error(f"Unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
