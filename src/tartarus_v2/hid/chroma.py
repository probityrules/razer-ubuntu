"""High-level Chroma / lighting / LED controls for Tartarus V2."""

from __future__ import annotations

import logging
from typing import Iterable

from tartarus_v2 import constants as C
from tartarus_v2.hid import protocol
from tartarus_v2.hid.device import TartarusDevice

log = logging.getLogger("tartarus_v2.chroma")


def _parse_rgb(value: str | tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(value, tuple):
        return value
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"RGB must be RRGGBB, got {value!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


class ChromaController:
    def __init__(self, device: TartarusDevice) -> None:
        self.device = device

    def _send(self, report: protocol.RazerReport, tx: int = C.TX_ID_EFFECTS) -> protocol.RazerReport:
        report.transaction_id = tx
        return self.device.send(report)

    def enter_driver_mode(self) -> None:
        self._send(protocol.set_device_mode(C.DRIVER_MODE), tx=C.TX_ID_EFFECTS)
        log.info("Entered driver mode")

    def leave_driver_mode(self) -> None:
        self._send(protocol.set_device_mode(C.NORMAL_MODE), tx=C.TX_ID_EFFECTS)
        log.info("Left driver mode (normal)")

    def get_firmware(self) -> str:
        resp = self._send(protocol.get_firmware_version(), tx=C.TX_ID_EFFECTS)
        major, minor = resp.arguments[0], resp.arguments[1]
        return f"v{major}.{minor}"

    def get_serial(self) -> str:
        resp = self._send(protocol.get_serial(), tx=C.TX_ID_EFFECTS)
        raw = bytes(resp.arguments[:22]).split(b"\x00", 1)[0]
        return raw.decode("ascii", errors="replace")

    def set_brightness(self, value: int) -> None:
        value = max(0, min(255, int(value)))
        # Tartarus V2 brightness quirk: ZERO_LED
        self._send(
            protocol.set_brightness(C.VARSTORE, C.ZERO_LED, value),
            tx=C.TX_ID_EFFECTS,
        )
        log.info("Brightness set to %s", value)

    def get_brightness(self) -> int:
        resp = self._send(
            protocol.get_brightness(C.VARSTORE, C.ZERO_LED),
            tx=C.TX_ID_EFFECTS,
        )
        return int(resp.arguments[2])

    def set_profile_led(self, color: str, enabled: bool) -> None:
        led_map = {
            "red": C.RED_PROFILE_LED,
            "green": C.GREEN_PROFILE_LED,
            "blue": C.BLUE_PROFILE_LED,
        }
        if color not in led_map:
            raise ValueError("color must be red, green, or blue")
        self._send(
            protocol.set_led_state(C.VARSTORE, led_map[color], enabled),
            tx=C.TX_ID_PROFILE_LED,
        )

    def set_game_led(self, enabled: bool) -> None:
        self._send(
            protocol.set_led_state(C.VARSTORE, C.GAME_LED, enabled),
            tx=C.TX_ID_PROFILE_LED,
        )

    def set_macro_led(self, enabled: bool) -> None:
        self._send(
            protocol.set_led_state(C.VARSTORE, C.MACRO_LED, enabled),
            tx=C.TX_ID_PROFILE_LED,
        )

    def set_effect_none(self) -> None:
        self._send(protocol.effect_none(C.VARSTORE, C.BACKLIGHT_LED))

    def set_effect_static(self, rgb: str | tuple[int, int, int]) -> None:
        r, g, b = _parse_rgb(rgb)
        self._send(protocol.effect_static(C.VARSTORE, C.BACKLIGHT_LED, r, g, b))
        log.info("Effect static #%02x%02x%02x", r, g, b)

    def set_effect_spectrum(self) -> None:
        self._send(protocol.effect_spectrum(C.VARSTORE, C.BACKLIGHT_LED))
        log.info("Effect spectrum")

    def set_effect_wave(self, direction: int = 1) -> None:
        self._send(protocol.effect_wave(C.VARSTORE, C.BACKLIGHT_LED, direction))
        log.info("Effect wave direction=%s", direction)

    def set_effect_reactive(
        self, rgb: str | tuple[int, int, int], speed: int = 2
    ) -> None:
        r, g, b = _parse_rgb(rgb)
        self._send(
            protocol.effect_reactive(C.VARSTORE, C.BACKLIGHT_LED, speed, r, g, b)
        )
        log.info("Effect reactive")

    def set_effect_breath(
        self,
        rgb: str | tuple[int, int, int] | None = None,
        rgb2: str | tuple[int, int, int] | None = None,
    ) -> None:
        if rgb is None:
            report = protocol.effect_breath_random(C.VARSTORE, C.BACKLIGHT_LED)
        elif rgb2 is None:
            r, g, b = _parse_rgb(rgb)
            report = protocol.effect_breath_single(C.VARSTORE, C.BACKLIGHT_LED, r, g, b)
        else:
            r1, g1, b1 = _parse_rgb(rgb)
            r2, g2, b2 = _parse_rgb(rgb2)
            report = protocol.effect_breath_dual(
                C.VARSTORE, C.BACKLIGHT_LED, r1, g1, b1, r2, g2, b2
            )
        self._send(report, tx=C.TX_ID_BREATH)
        log.info("Effect breath")

    def set_effect_starlight(
        self, rgb: str | tuple[int, int, int] | None = None, speed: int = 2
    ) -> None:
        if rgb is None:
            report = protocol.effect_starlight_random(
                C.VARSTORE, C.BACKLIGHT_LED, speed
            )
        else:
            r, g, b = _parse_rgb(rgb)
            report = protocol.effect_starlight_single(
                C.VARSTORE, C.BACKLIGHT_LED, speed, r, g, b
            )
        self._send(report)
        log.info("Effect starlight")

    def set_custom_frame(self, rows: Iterable[Iterable[tuple[int, int, int]]]) -> None:
        """rows: up to 4 rows of up to 6 (r,g,b) cells."""
        for row_idx, row in enumerate(rows):
            if row_idx >= C.MATRIX_ROWS:
                break
            cells = list(row)[: C.MATRIX_COLS]
            if not cells:
                continue
            rgb = bytearray()
            for r, g, b in cells:
                rgb.extend((r & 0xFF, g & 0xFF, b & 0xFF))
            stop = len(cells) - 1
            self._send(
                protocol.set_custom_frame_row(row_idx, 0, stop, bytes(rgb)),
                tx=C.TX_ID_EFFECTS,
            )
        self._send(protocol.effect_custom_frame(), tx=C.TX_ID_EFFECTS)
        log.info("Custom frame applied")

    def apply_lighting(self, lighting: dict) -> None:
        """Apply lighting section from a profile JSON."""
        effect = (lighting or {}).get("effect", "spectrum")
        brightness = lighting.get("brightness")
        if brightness is not None:
            self.set_brightness(int(brightness))

        if effect == "none":
            self.set_effect_none()
        elif effect == "static":
            self.set_effect_static(lighting.get("rgb", "00FF00"))
        elif effect == "spectrum":
            self.set_effect_spectrum()
        elif effect == "wave":
            self.set_effect_wave(int(lighting.get("direction", 1)))
        elif effect == "reactive":
            self.set_effect_reactive(
                lighting.get("rgb", "FF0000"), int(lighting.get("speed", 2))
            )
        elif effect == "breath":
            self.set_effect_breath(lighting.get("rgb"), lighting.get("rgb2"))
        elif effect == "starlight":
            self.set_effect_starlight(
                lighting.get("rgb"), int(lighting.get("speed", 2))
            )
        else:
            log.warning("Unknown effect %r; using spectrum", effect)
            self.set_effect_spectrum()
