"""USB HID transport for Tartarus V2 chroma control interface."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from tartarus_v2 import constants as C
from tartarus_v2.hid import protocol
from tartarus_v2.logging_util import annotate_report

log = logging.getLogger("tartarus_v2.hid")

# Interfaces 0 and 1 are both HID keyboards (boot + NKRO). Interface 2 is the
# mouse (scroll wheel). OpenRazer keeps hid-generic bound on the keyboard
# interfaces and sends chroma as a feature report on interface 1. Detaching
# interface 1 deletes if01-event-kbd, so the remap daemon never sees those
# keypresses and text editors plus the diagnostic listener stay silent.
KEYBOARD_INTERFACE = 0
NKRO_KEYBOARD_INTERFACE = 1
MOUSE_INTERFACE = 2
INPUT_INTERFACES = (KEYBOARD_INTERFACE, NKRO_KEYBOARD_INTERFACE, MOUSE_INTERFACE)

# linux/hidraw.h: _IOC(_IOC_WRITE|_IOC_READ, 'H', nr, len)
_HIDIOCSFEATURE_NR = 0x06
_HIDIOCGFEATURE_NR = 0x07


class DeviceError(RuntimeError):
    pass


def hid_feature_ioctl(nr: int, length: int) -> int:
    """Encode a hidraw feature-report ioctl for a buffer of ``length`` bytes."""
    return (3 << 30) | (length << 16) | (ord("H") << 8) | (nr & 0xFF)


def hidraw_matches(uevent: str, *, vendor: int, product: int, interface: int) -> bool:
    """True when a hidraw uevent is this keypad's ``interface`` (``.../inputN``)."""
    text = uevent.upper()
    if f"{vendor:08X}" not in text or f"{product:08X}" not in text:
        return False
    phys = ""
    for line in uevent.splitlines():
        if line.startswith("HID_PHYS="):
            phys = line.split("=", 1)[1].strip()
            break
    return phys.endswith(f"/input{interface}")


def find_tartarus_hidraw(interface: int, *, root: Path | None = None) -> str | None:
    """Return ``/dev/hidrawN`` for a Tartarus interface, or None."""
    base = root if root is not None else Path("/sys/class/hidraw")
    if not base.is_dir():
        return None
    for node in sorted(base.iterdir()):
        uevent_path = node / "device" / "uevent"
        try:
            uevent = uevent_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if hidraw_matches(
            uevent, vendor=C.USB_VID, product=C.USB_PID, interface=interface
        ):
            return f"/dev/{node.name}"
    return None


def pack_feature_report(payload: bytes) -> bytearray:
    """Prefix report id 0. The kernel strips it and sends ``payload`` as-is."""
    buf = bytearray(1 + len(payload))
    buf[0] = 0
    buf[1:] = payload
    return buf


def unpack_feature_report(buf: bytes | bytearray, size: int = C.REPORT_LEN) -> bytes:
    """Feature GET for report id 0 places the device bytes after the id."""
    data = bytes(buf[1 : 1 + size])
    if len(data) < size:
        data = data + bytes(size - len(data))
    return data


class TartarusDevice:
    """Chroma transport that leaves every key-emitting HID interface bound."""

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self._usb: Any = None
        self._fd: int | None = None
        self._hidraw_path: str | None = None
        self._claimed_iface: int | None = None
        self._detached_ifaces: list[int] = []

    def open(self) -> None:
        self._rebind_inputs()
        self._open_hidraw()

    def _import_usb(self) -> tuple[Any, Any]:
        try:
            import usb.core
            import usb.util
        except ImportError as exc:
            raise DeviceError(
                "pyusb is required. Install with: pip install pyusb"
            ) from exc
        return usb.core, usb.util

    def _rebind_inputs(self) -> None:
        """Put hid-generic back on any keyboard/mouse interface a prior open unbound."""
        usb_core, usb_util = self._import_usb()
        dev = usb_core.find(idVendor=C.USB_VID, idProduct=C.USB_PID)
        if dev is None:
            raise DeviceError(
                f"Device {C.USB_VID:04x}:{C.USB_PID:04x} not found. "
                "Is the Tartarus V2 plugged in?"
            )
        try:
            self._restore_unbound_inputs(dev)
        finally:
            try:
                usb_util.dispose_resources(dev)
            except Exception:  # noqa: BLE001
                pass

    def _open_hidraw(self) -> None:
        path = self._wait_hidraw(C.REPORT_INDEX)
        try:
            fd = os.open(path, os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
        except OSError as exc:
            raise DeviceError(
                f"Could not open {path} for chroma ({exc}). "
                "The kernel keyboard driver stays bound so keypresses are not "
                "lost. plugdev (or the tartarus udev rule) must be able to "
                "write that hidraw node."
            ) from exc
        self._fd = fd
        self._hidraw_path = path
        self._claimed_iface = C.REPORT_INDEX
        log.info(
            "Opened %s (%04x:%04x) via %s on interface %s "
            "(kernel driver left bound so keypad keys still arrive)",
            C.DEVICE_NAME,
            C.USB_VID,
            C.USB_PID,
            path,
            self._claimed_iface,
        )

    def _wait_hidraw(self, interface: int, timeout: float = 3.0) -> str:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            path = find_tartarus_hidraw(interface)
            if path:
                return path
            if time.monotonic() >= deadline:
                raise DeviceError(
                    f"No hidraw node for Tartarus interface {interface}. "
                    "Chroma uses that node without detaching hid-generic. "
                    "Unbinding it removes the second keyboard, and then neither "
                    "a text editor nor the diagnostic listener receives keys."
                )
            time.sleep(0.1)

    def _kernel_driver_active(self, dev: Any, iface: int) -> bool:
        try:
            return bool(dev.is_kernel_driver_active(iface))
        except Exception as exc:  # noqa: BLE001
            log.debug("is_kernel_driver_active(%s): %s", iface, exc)
            return False

    def _detach_kernel(self, dev: Any, iface: int) -> None:
        """Never detach a Tartarus interface. Keyboards and the mouse emit input."""
        if iface in INPUT_INTERFACES:
            log.error(
                "Refusing to detach kernel driver from input interface %s",
                iface,
            )
            return
        if not self._kernel_driver_active(dev, iface):
            return
        try:
            dev.detach_kernel_driver(iface)
        except Exception as exc:  # noqa: BLE001
            log.debug("detach_kernel_driver(%s): %s", iface, exc)
            return
        if iface not in self._detached_ifaces:
            self._detached_ifaces.append(iface)
        log.info("Detached kernel driver from interface %s", iface)

    def _restore_unbound_inputs(self, dev: Any) -> None:
        """Rebind hid-generic on every input interface a prior open left unbound."""
        for iface in INPUT_INTERFACES:
            if self._kernel_driver_active(dev, iface):
                continue
            try:
                dev.attach_kernel_driver(iface)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Input interface %s has no kernel driver and could not be rebound (%s). "
                    "Keys on that interface will not reach a text editor until the "
                    "keypad is replugged.",
                    iface,
                    exc,
                )
                continue
            log.info(
                "Reattached kernel driver on input interface %s "
                "(keypad events were unbound)",
                iface,
            )

    def _reattach_detached(self, dev: Any) -> None:
        for iface in list(self._detached_ifaces):
            try:
                dev.attach_kernel_driver(iface)
                log.info("Reattached kernel driver on interface %s", iface)
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "Could not reattach kernel driver on interface %s (%s). "
                    "Replug the keypad if it stops sending keys.",
                    iface,
                    exc,
                )
            finally:
                try:
                    self._detached_ifaces.remove(iface)
                except ValueError:
                    pass

    def close(self) -> None:
        fd = self._fd
        self._fd = None
        self._hidraw_path = None
        self._claimed_iface = None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            pass

    def __enter__(self) -> TartarusDevice:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def report_index(self) -> int:
        return self._claimed_iface if self._claimed_iface is not None else C.REPORT_INDEX

    def send(self, report: protocol.RazerReport) -> protocol.RazerReport:
        if self._fd is None:
            raise DeviceError("Device not open")

        if report.transaction_id == 0:
            report.transaction_id = C.TX_ID_EFFECTS

        request = report.to_bytes()
        last_err: Exception | None = None

        for attempt in range(1, C.MAX_RETRIES + 1):
            try:
                if self.debug:
                    log.debug("TX attempt %s:\n%s", attempt, annotate_report(request))

                self._feature_io(request, write=True)
                time.sleep(C.WAIT_SECONDS)
                response = self._feature_io(bytes(C.REPORT_LEN), write=False)
                if self.debug:
                    log.debug("RX attempt %s:\n%s", attempt, annotate_report(response))

                parsed = protocol.RazerReport.from_bytes(response)
                if parsed.status == C.CMD_BUSY:
                    time.sleep(C.WAIT_SECONDS * 2)
                    continue
                if parsed.status in (C.CMD_FAILURE, C.CMD_TIMEOUT, C.CMD_NOT_SUPPORTED):
                    raise DeviceError(
                        f"Device rejected command status=0x{parsed.status:02x} "
                        f"class=0x{report.command_class:02x} cmd=0x{report.command_id:02x}"
                    )
                return parsed
            except DeviceError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                log.debug("send attempt %s failed: %s", attempt, exc)
                time.sleep(C.WAIT_SECONDS * attempt)

        raise DeviceError(f"USB transfer failed after retries: {last_err}")

    def _feature_io(self, payload: bytes, *, write: bool) -> bytes:
        import fcntl

        fd = self._fd
        if fd is None:
            raise DeviceError("Device not open")
        if write:
            buf = pack_feature_report(payload)
            fcntl.ioctl(fd, hid_feature_ioctl(_HIDIOCSFEATURE_NR, len(buf)), buf, True)
            return payload
        buf = pack_feature_report(bytes(C.REPORT_LEN))
        fcntl.ioctl(fd, hid_feature_ioctl(_HIDIOCGFEATURE_NR, len(buf)), buf, True)
        return unpack_feature_report(buf)
