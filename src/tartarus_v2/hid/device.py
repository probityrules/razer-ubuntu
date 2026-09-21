"""USB HID transport for Tartarus V2 chroma control interface."""

from __future__ import annotations

import logging
import time
from typing import Any

from tartarus_v2 import constants as C
from tartarus_v2.hid import protocol
from tartarus_v2.logging_util import annotate_report

log = logging.getLogger("tartarus_v2.hid")


class DeviceError(RuntimeError):
    pass


class TartarusDevice:
    """Low-level USB control-transfer transport (OpenRazer-compatible framing)."""

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self._usb: Any = None
        self._claimed_iface: int | None = None
        self._detached = False

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

        # Prefer interface matching REPORT_INDEX; fall back to first available.
        iface = C.REPORT_INDEX
        try:
            if dev.is_kernel_driver_active(iface):
                dev.detach_kernel_driver(iface)
                self._detached = True
                log.info("Detached kernel driver from interface %s", iface)
        except (usb.core.USBError, NotImplementedError, ValueError) as exc:
            log.debug("detach_kernel_driver(%s): %s", iface, exc)

        try:
            usb.util.claim_interface(dev, iface)
            self._claimed_iface = iface
        except usb.core.USBError as exc:
            # Try alternate interfaces 0..2
            claimed = False
            for alt in (0, 1, 2):
                if alt == iface:
                    continue
                try:
                    if dev.is_kernel_driver_active(alt):
                        dev.detach_kernel_driver(alt)
                        self._detached = True
                    usb.util.claim_interface(dev, alt)
                    self._claimed_iface = alt
                    iface = alt
                    claimed = True
                    log.warning("Claimed alternate interface %s", alt)
                    break
                except usb.core.USBError:
                    continue
            if not claimed:
                raise DeviceError(
                    f"Could not claim USB interface (tried {C.REPORT_INDEX} and 0-2): {exc}"
                ) from exc

        self._usb = dev
        log.info(
            "Opened %s (%04x:%04x) on interface %s",
            C.DEVICE_NAME,
            C.USB_VID,
            C.USB_PID,
            self._claimed_iface,
        )

    def close(self) -> None:
        if self._usb is None:
            return
        try:
            import usb.util

            if self._claimed_iface is not None:
                try:
                    usb.util.release_interface(self._usb, self._claimed_iface)
                except Exception:  # noqa: BLE001
                    pass
            if self._detached and self._claimed_iface is not None:
                try:
                    self._usb.attach_kernel_driver(self._claimed_iface)
                except Exception:  # noqa: BLE001
                    pass
            usb.util.dispose_resources(self._usb)
        finally:
            self._usb = None
            self._claimed_iface = None
            self._detached = False

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
