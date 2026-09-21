"""Paste-ready diagnostic dump for remote Windows↔Linux debugging."""

from __future__ import annotations

import argparse
import glob
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from tartarus_v2 import __version__
from tartarus_v2 import constants as C
from tartarus_v2.logging_util import annotate_report, log_path


COPY_FROM = "=== COPY FROM HERE ==="
COPY_TO = "=== COPY TO HERE ==="


def _run(cmd: list[str], timeout: float = 10.0) -> str:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return out.strip() or f"(exit {proc.returncode}, no output)"
    except FileNotFoundError:
        return f"(command not found: {cmd[0]})"
    except subprocess.TimeoutExpired:
        return f"(timeout running {' '.join(cmd)})"
    except Exception as exc:  # noqa: BLE001
        return f"(error: {exc})"


def _section(title: str, body: str) -> str:
    bar = "=" * 72
    return f"\n{bar}\n## {title}\n{bar}\n{body.rstrip()}\n"


def _read_text(path: Path, limit: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if limit is not None:
            lines = text.splitlines()
            text = "\n".join(lines[-limit:])
        return text
    except Exception as exc:  # noqa: BLE001
        return f"(could not read {path}: {exc})"


def _header() -> str:
    lines = [
        f"tool=tartarus-v2 version={__version__}",
        f"utc={datetime.now(timezone.utc).isoformat()}",
        f"hostname={platform.node()}",
        f"platform={platform.platform()}",
        f"python={platform.python_version()}",
        f"uname={_run(['uname', '-a'])}",
    ]
    os_release = Path("/etc/os-release")
    if os_release.exists():
        lines.append("--- /etc/os-release ---")
        lines.append(_read_text(os_release))
    return "\n".join(lines)


def _device_usb() -> str:
    out = [
        _run(["lsusb", "-d", f"{C.USB_VID:04x}:{C.USB_PID:04x}"]),
        "",
        "--- lsusb -v (truncated interest lines) ---",
    ]
    verbose = _run(
        ["lsusb", "-d", f"{C.USB_VID:04x}:{C.USB_PID:04x}", "-v"],
        timeout=20,
    )
    keep = []
    for line in verbose.splitlines():
        low = line.lower()
        if any(
            k in low
            for k in (
                "idvendor",
                "idproduct",
                "bcddevice",
                "iManufacturer".lower(),
                "iproduct",
                "iserial",
                "binterface",
                "binterfacenumber",
                "binterfaceclass",
                "binterfaceprotocol",
                "hid",
            )
        ):
            keep.append(line)
    out.append("\n".join(keep) if keep else verbose[:4000])
    return "\n".join(out)


def _hid_inventory() -> str:
    lines: list[str] = []
    hidraw = sorted(glob.glob("/dev/hidraw*"))
    lines.append(f"hidraw nodes: {hidraw or '(none)'}")
    sys_hid = Path("/sys/class/hidraw")
    if sys_hid.is_dir():
        for node in sorted(sys_hid.iterdir()):
            device = node / "device"
            uevent = device / "uevent"
            driver = ""
            try:
                drv = (device / "driver").resolve()
                driver = drv.name
            except Exception:  # noqa: BLE001
                driver = "(unknown)"
            ue = _read_text(uevent) if uevent.exists() else ""
            interesting = (
                "022B" in ue.upper()
                or "1532" in ue.upper()
                or "TARTARUS" in ue.upper()
            )
            if interesting:
                lines.append(f"\n{node.name}: driver={driver}")
                lines.append(ue)
    # Also list HID devices under /sys/bus/hid/devices
    hid_bus = Path("/sys/bus/hid/devices")
    if hid_bus.is_dir():
        lines.append("\n--- /sys/bus/hid/devices matching 1532:022B ---")
        for d in sorted(hid_bus.iterdir()):
            if "1532:022B" in d.name.upper() or "1532:022B" in d.name:
                drv = ""
                try:
                    drv = (d / "driver").resolve().name
                except Exception:  # noqa: BLE001
                    drv = "(unbound?)"
                lines.append(f"{d.name} driver={drv}")
    return "\n".join(lines) if lines else "(no hid sysfs)"


def _input_nodes() -> str:
    lines = ["--- /dev/input/by-id (*Tartarus*) ---"]
    by_id = Path("/dev/input/by-id")
    if by_id.is_dir():
        matches = sorted(p for p in by_id.iterdir() if "tartarus" in p.name.lower())
        if not matches:
            lines.append("(none)")
        for p in matches:
            try:
                target = p.resolve()
                lines.append(f"{p.name} -> {target}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"{p.name} (error: {exc})")
    else:
        lines.append("(no /dev/input/by-id)")
    lines.append("\n--- evdev name scan ---")
    try:
        import evdev

        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            if "tartarus" in (dev.name or "").lower() or "1532" in (dev.phys or ""):
                lines.append(f"{path}: name={dev.name!r} phys={dev.phys!r}")
    except ImportError:
        lines.append("(evdev not installed)")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"(evdev scan error: {exc})")
    return "\n".join(lines)


def _conflict_check() -> str:
    lsmod_out = _run(["bash", "-lc", "lsmod | grep -i razer || true"])
    dkms_out = _run(["bash", "-lc", "dkms status 2>/dev/null | grep -i openrazer || true"])
    pkg_cmd = "dpkg -l 'openrazer*' 2>/dev/null | tail -n +6 || true"
    packages_out = _run(["bash", "-lc", pkg_cmd])
    lines = [
        f"lsmod razer*: {lsmod_out}",
        f"dkms: {dkms_out}",
        f"packages: {packages_out}",
    ]
    bound = False
    hid_bus = Path("/sys/bus/hid/devices")
    if hid_bus.is_dir():
        for d in hid_bus.iterdir():
            if "1532:022B" not in d.name.upper() and "1532:022B" not in d.name:
                continue
            try:
                drv = (d / "driver").resolve().name
            except Exception:  # noqa: BLE001
                continue
            if drv == "razerkbd":
                bound = True
                lines.append(f"BOUND: {d.name} -> razerkbd")
                lines.append(
                    "Unbind suggestion:\n"
                    f"  echo -n '{d.name}' | sudo tee /sys/bus/hid/drivers/razerkbd/unbind\n"
                    "  # then re-plug or bind to hid-generic if needed"
                )
    if not bound:
        lines.append("No razerkbd binding detected for 1532:022B (good for this driver).")
    return "\n".join(lines)


def _permissions() -> str:
    import getpass

    user = getpass.getuser()
    groups: list[str] = []
    try:
        import grp

        groups = [g.gr_name for g in grp.getgrall() if user in g.gr_mem]
        groups.append(grp.getgrgid(os.getgid()).gr_name)
    except ImportError:
        groups = ["(grp module unavailable on this OS)"]
    except Exception as exc:  # noqa: BLE001
        groups = [f"(error listing groups: {exc})"]
    lines = [
        f"user={user}",
        f"groups={sorted(set(groups))}",
        f"in_input={'input' in groups}",
        f"in_plugdev={'plugdev' in groups}",
        "udev rules:",
    ]
    for pattern in (
        "/etc/udev/rules.d/*tartarus*",
        "/etc/udev/rules.d/*razer*",
        "/lib/udev/rules.d/*razer*",
    ):
        hits = glob.glob(pattern)
        if hits:
            for h in hits:
                lines.append(f"  {h}")
        else:
            lines.append(f"  (no matches for {pattern})")
    return "\n".join(lines)


def _live_probe(debug: bool = True) -> str:
    lines: list[str] = []
    try:
        from tartarus_v2.hid.chroma import ChromaController
        from tartarus_v2.hid.device import TartarusDevice
        from tartarus_v2.hid import protocol

        with TartarusDevice(debug=debug) as dev:
            chroma = ChromaController(dev)
            lines.append(f"claimed_interface={dev.report_index}")

            # firmware
            req = protocol.get_firmware_version()
            req.transaction_id = C.TX_ID_EFFECTS
            raw_tx = req.to_bytes()
            lines.append("TX get_firmware:")
            lines.append(annotate_report(raw_tx))
            resp = dev.send(req)
            lines.append("RX get_firmware:")
            lines.append(annotate_report(resp.to_bytes()))
            lines.append(f"firmware={chroma.get_firmware()}")

            req = protocol.get_serial()
            req.transaction_id = C.TX_ID_EFFECTS
            resp = dev.send(req)
            lines.append("RX get_serial:")
            lines.append(annotate_report(resp.to_bytes()))
            serial = bytes(resp.arguments[:22]).split(b"\x00", 1)[0]
            lines.append(f"serial={serial!r}")

            req = protocol.get_brightness(C.VARSTORE, C.ZERO_LED)
            req.transaction_id = C.TX_ID_EFFECTS
            resp = dev.send(req)
            lines.append("RX get_brightness (ZERO_LED):")
            lines.append(annotate_report(resp.to_bytes()))
            lines.append(f"brightness={resp.arguments[2]}")
            lines.append("live probe: OK")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"live probe FAILED: {type(exc).__name__}: {exc}")
    return "\n".join(lines)


def _listen(seconds: float) -> str:
    lines = [f"Listening {seconds}s for Tartarus key events..."]
    try:
        import select

        import evdev
        from evdev import ecodes

        from tartarus_v2.input.keys import CODE_TO_LOGICAL

        devices = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
            except OSError:
                continue
            if "tartarus" in (d.name or "").lower():
                devices.append(d)
        if not devices:
            return "No Tartarus evdev devices to listen on."
        for d in devices:
            lines.append(f"watching {d.path} ({d.name})")
        fds = {d.fd: d for d in devices}
        end = time.time() + seconds
        while time.time() < end:
            timeout = max(0.0, end - time.time())
            r, _, _ = select.select(list(fds), [], [], timeout)
            for fd in r:
                for event in fds[fd].read():
                    if event.type == ecodes.EV_KEY and event.value != 2:
                        logical = CODE_TO_LOGICAL.get(event.code, "?")
                        lines.append(
                            f"KEY code={event.code} logical={logical} value={event.value}"
                        )
                    elif event.type == ecodes.EV_REL:
                        lines.append(
                            f"REL code={event.code} value={event.value}"
                        )
    except ImportError:
        return "(evdev not installed; cannot listen)"
    except Exception as exc:  # noqa: BLE001
        return f"(listen error: {exc})"
    return "\n".join(lines)


def _log_tail() -> str:
    path = log_path()
    lines = [f"daemon log: {path}"]
    if path.exists():
        lines.append(_read_text(path, limit=80))
    else:
        lines.append("(no daemon log yet)")
    lines.append("\n--- dmesg (hid/razer, last matches) ---")
    dmesg = _run(["bash", "-lc", "dmesg -T 2>/dev/null | grep -iE 'razer|hidraw|1532' | tail -n 40 || true"])
    lines.append(dmesg or "(no matches)")
    return "\n".join(lines)


def build_report(listen_seconds: float = 0.0, skip_probe: bool = False) -> str:
    parts = [
        COPY_FROM,
        _section("1. Header", _header()),
        _section("2. Device USB", _device_usb()),
        _section("3. HID inventory", _hid_inventory()),
        _section("4. Input nodes", _input_nodes()),
        _section("5. Conflict check (OpenRazer)", _conflict_check()),
        _section("6. Permissions", _permissions()),
    ]
    if skip_probe:
        parts.append(_section("7. Live probe", "(skipped)"))
    else:
        parts.append(_section("7. Live probe", _live_probe()))
    if listen_seconds > 0:
        parts.append(_section("8. Key listen", _listen(listen_seconds)))
    else:
        parts.append(_section("8. Key listen", "(skipped; pass --listen N)"))
    parts.append(_section("9. Log tail", _log_tail()))
    parts.append(f"\n{COPY_TO}\n")
    return "\n".join(parts)


def run_diagnose(args: argparse.Namespace) -> int:
    report = build_report(
        listen_seconds=float(args.listen or 0),
        skip_probe=bool(args.skip_probe),
    )
    print(report)
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\nWrote {out}", flush=True)
    return 0
