"""Session daemon: lighting + remapper."""

from __future__ import annotations

import logging
import signal
from typing import Any

from tartarus_v2.hid.chroma import ChromaController
from tartarus_v2.hid.device import TartarusDevice
from tartarus_v2.input.remapper import Remapper
from tartarus_v2.profiles import (
    cycle_profile,
    get_active_profile_name,
    load_profile,
    set_active_profile_name,
)

log = logging.getLogger("tartarus_v2.daemon")


class Daemon:
    def __init__(self, profile_name: str | None = None, debug: bool = False) -> None:
        self.debug = debug
        self.profile_name = profile_name or get_active_profile_name()
        self.profile: dict[str, Any] = {}
        self._device: TartarusDevice | None = None
        self._chroma: ChromaController | None = None
        self._remapper: Remapper | None = None
        self._stop = False

    def _on_profile_switch(self, direction: str) -> None:
        name = cycle_profile(direction)
        log.info("Active profile -> %s", name)
        self.profile_name = name
        self.profile = load_profile(name)
        if self._chroma is not None:
            try:
                self._chroma.apply_lighting(self.profile.get("lighting") or {})
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to apply lighting for %s: %s", name, exc)
        if self._remapper is not None:
            self._remapper.profile = self.profile

    def start(self) -> None:
        set_active_profile_name(self.profile_name)
        self.profile = load_profile(self.profile_name)
        log.info("Starting daemon with profile=%s", self.profile_name)

        self._device = TartarusDevice(debug=self.debug)
        try:
            self._device.open()
            self._chroma = ChromaController(self._device)
            self._chroma.enter_driver_mode()
            self._chroma.apply_lighting(self.profile.get("lighting") or {})
        except Exception as exc:  # noqa: BLE001
            log.error("Chroma init failed (remap will still run): %s", exc)
            if self._device is not None:
                try:
                    self._device.close()
                except Exception:  # noqa: BLE001
                    pass
                self._device = None
                self._chroma = None

        self._remapper = Remapper(
            self.profile,
            debug=self.debug,
            on_profile_switch=self._on_profile_switch,
        )

        def _handle_sig(_signum: int, _frame: Any) -> None:
            log.info("Signal received; stopping")
            self._stop = True
            if self._remapper is not None:
                self._remapper._running = False

        signal.signal(signal.SIGINT, _handle_sig)
        signal.signal(signal.SIGTERM, _handle_sig)

        try:
            self._remapper.start()
            self._remapper.run_forever()
        finally:
            self.stop()

    def stop(self) -> None:
        if self._remapper is not None:
            self._remapper.stop()
            self._remapper = None
        if self._chroma is not None:
            try:
                self._chroma.leave_driver_mode()
            except Exception:  # noqa: BLE001
                pass
            self._chroma = None
        if self._device is not None:
            self._device.close()
            self._device = None
        log.info("Daemon stopped")
