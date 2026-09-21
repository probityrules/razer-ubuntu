"""90-byte Razer HID report framing (protocol referenced from OpenRazer)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tartarus_v2.constants import REPORT_LEN


@dataclass
class RazerReport:
    status: int = 0
    transaction_id: int = 0
    remaining_packets: int = 0
    protocol_type: int = 0
    data_size: int = 0
    command_class: int = 0
    command_id: int = 0
    arguments: bytearray = field(default_factory=lambda: bytearray(80))
    crc: int = 0
    reserved: int = 0

    def to_bytes(self) -> bytes:
        buf = bytearray(REPORT_LEN)
        buf[0] = self.status & 0xFF
        buf[1] = self.transaction_id & 0xFF
        buf[2:4] = int(self.remaining_packets).to_bytes(2, "big")
        buf[4] = self.protocol_type & 0xFF
        buf[5] = self.data_size & 0xFF
        buf[6] = self.command_class & 0xFF
        buf[7] = self.command_id & 0xFF
        args = bytes(self.arguments)[:80]
        buf[8 : 8 + len(args)] = args
        buf[88] = calculate_crc(buf)
        buf[89] = self.reserved & 0xFF
        self.crc = buf[88]
        return bytes(buf)

    @classmethod
    def from_bytes(cls, data: bytes | bytearray) -> RazerReport:
        if len(data) < REPORT_LEN:
            data = bytes(data) + bytes(REPORT_LEN - len(data))
        args = bytearray(80)
        args[:80] = data[8:88]
        return cls(
            status=data[0],
            transaction_id=data[1],
            remaining_packets=int.from_bytes(data[2:4], "big"),
            protocol_type=data[4],
            data_size=data[5],
            command_class=data[6],
            command_id=data[7],
            arguments=args,
            crc=data[88],
            reserved=data[89],
        )


def calculate_crc(report: bytes | bytearray) -> int:
    crc = 0
    for i in range(2, 88):
        crc ^= report[i]
    return crc & 0xFF


def get_razer_report(command_class: int, command_id: int, data_size: int) -> RazerReport:
    return RazerReport(
        command_class=command_class & 0xFF,
        command_id=command_id & 0xFF,
        data_size=data_size & 0xFF,
    )


def set_device_mode(mode: int, param: int = 0) -> RazerReport:
    report = get_razer_report(0x00, 0x04, 0x02)
    report.arguments[0] = 0x00 if mode not in (0x00, 0x03) else mode
    report.arguments[1] = 0x00
    return report


def get_device_mode() -> RazerReport:
    return get_razer_report(0x00, 0x84, 0x02)


def get_serial() -> RazerReport:
    return get_razer_report(0x00, 0x82, 0x16)


def get_firmware_version() -> RazerReport:
    return get_razer_report(0x00, 0x81, 0x02)


def set_led_state(variable_storage: int, led_id: int, led_state: int) -> RazerReport:
    report = get_razer_report(0x03, 0x00, 0x03)
    report.arguments[0] = variable_storage
    report.arguments[1] = led_id
    report.arguments[2] = 1 if led_state else 0
    return report


def get_led_state(variable_storage: int, led_id: int) -> RazerReport:
    report = get_razer_report(0x03, 0x80, 0x03)
    report.arguments[0] = variable_storage
    report.arguments[1] = led_id
    return report


def _extended_matrix_effect_base(
    arg_size: int, variable_storage: int, led_id: int, effect_id: int
) -> RazerReport:
    report = get_razer_report(0x0F, 0x02, arg_size)
    report.arguments[0] = variable_storage
    report.arguments[1] = led_id
    report.arguments[2] = effect_id
    return report


def effect_none(variable_storage: int, led_id: int) -> RazerReport:
    return _extended_matrix_effect_base(0x06, variable_storage, led_id, 0x00)


def effect_static(variable_storage: int, led_id: int, r: int, g: int, b: int) -> RazerReport:
    report = _extended_matrix_effect_base(0x09, variable_storage, led_id, 0x01)
    report.arguments[5] = 0x01
    report.arguments[6] = r & 0xFF
    report.arguments[7] = g & 0xFF
    report.arguments[8] = b & 0xFF
    return report


def effect_wave(variable_storage: int, led_id: int, direction: int) -> RazerReport:
    report = _extended_matrix_effect_base(0x06, variable_storage, led_id, 0x04)
    report.arguments[3] = max(0, min(2, direction))
    report.arguments[4] = 0x28
    return report


def effect_spectrum(variable_storage: int, led_id: int) -> RazerReport:
    return _extended_matrix_effect_base(0x06, variable_storage, led_id, 0x03)


def effect_reactive(
    variable_storage: int, led_id: int, speed: int, r: int, g: int, b: int
) -> RazerReport:
    report = _extended_matrix_effect_base(0x09, variable_storage, led_id, 0x05)
    report.arguments[4] = max(1, min(4, speed))
    report.arguments[5] = 0x01
    report.arguments[6] = r & 0xFF
    report.arguments[7] = g & 0xFF
    report.arguments[8] = b & 0xFF
    return report


def effect_breath_random(variable_storage: int, led_id: int) -> RazerReport:
    return _extended_matrix_effect_base(0x06, variable_storage, led_id, 0x02)


def effect_breath_single(
    variable_storage: int, led_id: int, r: int, g: int, b: int
) -> RazerReport:
    report = _extended_matrix_effect_base(0x09, variable_storage, led_id, 0x02)
    report.arguments[3] = 0x01
    report.arguments[5] = 0x01
    report.arguments[6] = r & 0xFF
    report.arguments[7] = g & 0xFF
    report.arguments[8] = b & 0xFF
    return report


def effect_breath_dual(
    variable_storage: int,
    led_id: int,
    r1: int,
    g1: int,
    b1: int,
    r2: int,
    g2: int,
    b2: int,
) -> RazerReport:
    report = _extended_matrix_effect_base(0x0C, variable_storage, led_id, 0x02)
    report.arguments[3] = 0x02
    report.arguments[5] = 0x02
    report.arguments[6] = r1 & 0xFF
    report.arguments[7] = g1 & 0xFF
    report.arguments[8] = b1 & 0xFF
    report.arguments[9] = r2 & 0xFF
    report.arguments[10] = g2 & 0xFF
    report.arguments[11] = b2 & 0xFF
    return report


def effect_starlight_random(variable_storage: int, led_id: int, speed: int) -> RazerReport:
    report = _extended_matrix_effect_base(0x06, variable_storage, led_id, 0x07)
    report.arguments[4] = max(1, min(3, speed))
    return report


def effect_starlight_single(
    variable_storage: int, led_id: int, speed: int, r: int, g: int, b: int
) -> RazerReport:
    report = _extended_matrix_effect_base(0x09, variable_storage, led_id, 0x07)
    report.arguments[4] = max(1, min(3, speed))
    report.arguments[5] = 0x01
    report.arguments[6] = r & 0xFF
    report.arguments[7] = g & 0xFF
    report.arguments[8] = b & 0xFF
    return report


def effect_custom_frame() -> RazerReport:
    return _extended_matrix_effect_base(0x0C, 0x00, 0x00, 0x08)


def set_custom_frame_row(
    row_index: int, start_col: int, stop_col: int, rgb_data: bytes
) -> RazerReport:
    report = get_razer_report(0x0F, 0x03, 0x47)
    report.arguments[2] = row_index & 0xFF
    report.arguments[3] = start_col & 0xFF
    report.arguments[4] = stop_col & 0xFF
    row_len = ((stop_col + 1) - start_col) * 3
    report.arguments[5 : 5 + row_len] = rgb_data[:row_len]
    return report


def set_brightness(variable_storage: int, led_id: int, brightness: int) -> RazerReport:
    report = get_razer_report(0x0F, 0x04, 0x03)
    report.arguments[0] = variable_storage
    report.arguments[1] = led_id
    report.arguments[2] = brightness & 0xFF
    return report


def get_brightness(variable_storage: int, led_id: int) -> RazerReport:
    report = get_razer_report(0x0F, 0x84, 0x03)
    report.arguments[0] = variable_storage
    report.arguments[1] = led_id
    return report
