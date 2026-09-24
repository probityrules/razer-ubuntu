"""USB HID transport for Tartarus V2 chroma control interface."""

from __future__ import annotations

import logging
import time
from typing import Any

from tartarus_v2 import constants as C
from tartarus_v2.hid import protocol
from tartarus_v2.logging_util import annotate_report

log = logging.getLogger("tartarus_v2.hid")

# Interface 0 is the boot keyboard and interface 2 is the mouse. The remap
# daemon reads those evdev nodes (interface 1 is held for chroma). Detaching
# either input interface deletes the node mid-read; the remapper then dies
# with ENODEV and text editors receive no keys, including firmware defaults.
KEYBOARD_INTERFACE = 0
MOUSE_INTERFACE = 2
INPUT_INTERFACES = (KEYBOARD_INTERFACE, MOUSE_INTERFACE)


class DeviceError(RuntimeError):
    pass


class TartarusDevice:
    """Low-level USB control-transfer transport (OpenRazer-compatible framing)."""

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self._usb: Any = None
        self._claimed_iface: int | None = None
        self._detached_ifaces: list[int] = []

    def open(self) -> None:
        try:
            import usb.core
            import usb.util
        except ImportError as exc:
            raise DeviceError(
                "pyusb is required. Install with: pip install pyusb"
            ) from exc

        dev = usb.core.find(idVendor=C.USB_VID, idProduct=C.USB_PID)
        if dev is None:
            raise DeviceError(
                f"Device {C.USB_VID:04x}:{C.USB_PID:04x} not found. "
                "Is the Tartarus V2 plugged in?"
            )

        # Heal a keypad left unbound by an earlier alternate-interface claim.
        self._restore_unbound_inputs(dev)

        iface = C.REPORT_INDEX
        self._detach_kernel(dev, iface)
        try:
            usb.util.claim_interface(dev, iface)
        except usb.core.USBError as exc:
            # Do not fall back onto interface 0 or 2. Those still have hid-generic
            # bound so the desktop can see key and mouse events. Claiming them
            # requires detaching that driver, which is what kills the remapper
            # when the GUI or diagnose probe opens the device while the daemon
            # already owns interface 1.
            self._reattach_detached(dev)
            try:
                usb.util.dispose_resources(dev)
            except Exception:  # noqa: BLE001
                pass
            raise DeviceError(
                f"Could not claim USB interface {iface} ({exc}). "
                "If the remap daemon is running it already owns this interface. "
                "Refusing to detach the keyboard or mouse interface, because that "
                "stops every key — including firmware defaults — from reaching "
                "text editors."
            ) from exc

        self._claimed_iface = iface
        self._usb = dev
        log.info(
            "Opened %s (%04x:%04x) on interface %s",
            C.DEVICE_NAME,
            C.USB_VID,
            C.USB_PID,
            self._claimed_iface,
        )

    def _kernel_driver_active(self, dev: Any, iface: int) -> bool:
        try:
            return bool(dev.is_kernel_driver_active(iface))
        except Exception as exc:  # noqa: BLE001
            log.debug("is_kernel_driver_active(%s): %s", iface, exc)
            return False

    def _detach_kernel(self, dev: Any, iface: int) -> None:
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
        """Rebind hid-generic on the keyboard and mouse if a prior open left them unbound."""
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
        if self._usb is None:
            return
        dev = self._usb
        try:
            import usb.util

            if self._claimed_iface is not None:
                try:
                    usb.util.release_interface(dev, self._claimed_iface)
                except Exception:  # noqa: BLE001
                    pass
            self._reattach_detached(dev)
            # If some other opener unbound the keyboard, put it back now that
            # we are releasing the device.
            self._restore_unbound_inputs(dev)
            usb.util.dispose_resources(dev)
        finally:
            self._usb = None
            self._claimed_iface = None
            self._detached_ifaces = []

    def __enter__(self) -> TartarusDevice:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def report_index(self) -> int:
        return self._claimed_iface if self._claimed_iface is not None else C.REPORT_INDEX

    def send(self, report: protocol.RazerReport) -> protocol.RazerReport:
        if self._usb is None:
            raise DeviceError("Device not open")

        if report.transaction_id == 0:
            report.transaction_id = C.TX_ID_EFFECTS

        request = report.to_bytes()
        last_err: Exception | None = None

        for attempt in range(1, C.MAX_RETRIES + 1):
            try:
                if self.debug:
                    log.debug("TX attempt %s:\n%s", attempt, annotate_report(request))

                self._usb.ctrl_transfer(
                    0x21,  # HOST_TO_DEVICE | CLASS | INTERFACE
                    0x09,  # SET_REPORT
                    C.REPORT_VALUE,
                    self.report_index,
                    request,
                    timeout=5000,
                )
                time.sleep(C.WAIT_SECONDS)

                response = bytes(
                    self._usb.ctrl_transfer(
                        0xA1,  # DEVICE_TO_HOST | CLASS | INTERFACE
                        0x01,  # GET_REPORT
                        C.REPORT_VALUE,
                        self.report_index,
                        C.REPORT_LEN,
                        timeout=5000,
                    )
                )
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
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                log.debug("send attempt %s failed: %s", attempt, exc)
                time.sleep(C.WAIT_SECONDS * attempt)

        raise DeviceError(f"USB transfer failed after retries: {last_err}")
