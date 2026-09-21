"""Protocol unit tests (run on Windows or Linux without hardware)."""

from __future__ import annotations

from tartarus_v2.hid import protocol
from tartarus_v2.constants import REPORT_LEN


def test_report_length_and_crc() -> None:
    report = protocol.effect_static(0x01, 0x05, 0xFF, 0x00, 0x00)
    report.transaction_id = 0x1F
    raw = report.to_bytes()
    assert len(raw) == REPORT_LEN
    assert raw[88] == protocol.calculate_crc(raw)
    assert raw[1] == 0x1F
    assert raw[6] == 0x0F
    assert raw[7] == 0x02
    assert raw[8 + 6] == 0xFF


def test_roundtrip() -> None:
    report = protocol.get_firmware_version()
    report.transaction_id = 0x1F
    raw = report.to_bytes()
    again = protocol.RazerReport.from_bytes(raw)
    assert again.command_class == 0x00
    assert again.command_id == 0x81
    assert again.data_size == 0x02


def test_brightness_uses_zero_led_args() -> None:
    report = protocol.set_brightness(0x01, 0x00, 200)
    assert report.arguments[0] == 0x01
    assert report.arguments[1] == 0x00
    assert report.arguments[2] == 200
