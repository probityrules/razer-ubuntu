"""Second USB opens must not unbind the keypad while the daemon is running."""

from __future__ import annotations

import errno
import os
import sys
from types import ModuleType

import pytest

from tartarus_v2 import actions, daemon_control, profiles
from tartarus_v2.diagnose import daemon_log_findings
from tartarus_v2.hid.device import (
    INPUT_INTERFACES,
    DeviceError,
    TartarusDevice,
    find_tartarus_hidraw,
    hid_feature_ioctl,
    hidraw_matches,
    pack_feature_report,
    unpack_feature_report,
)
from tartarus_v2.input.remapper import Remapper, input_node_lost_message


class _FakeDev:
    def __init__(self, active: set[int], *, claim_fail: set[int] | None = None) -> None:
        self.active = set(active)
        self.claim_fail = set(claim_fail or ())
        self.claimed: list[int] = []
        self.released: list[int] = []
        self.detached: list[int] = []
        self.attached: list[int] = []

    def is_kernel_driver_active(self, iface: int) -> bool:
        return iface in self.active

    def detach_kernel_driver(self, iface: int) -> None:
        self.detached.append(iface)
        self.active.discard(iface)

    def attach_kernel_driver(self, iface: int) -> None:
        self.attached.append(iface)
        self.active.add(iface)


def _install_usb(dev: _FakeDev) -> type[Exception]:
    usb = ModuleType("usb")
    core = ModuleType("usb.core")
    util = ModuleType("usb.util")

    class USBError(Exception):
        pass

    core.USBError = USBError
    core.find = lambda **_kwargs: dev

    def claim(device: _FakeDev, iface: int) -> None:
        if iface in device.claim_fail:
            raise USBError(f"busy {iface}")
        device.claimed.append(iface)

    util.claim_interface = claim
    util.release_interface = lambda device, iface: device.released.append(iface)
    util.dispose_resources = lambda _device: None
    usb.core = core
    usb.util = util
    sys.modules["usb"] = usb
    sys.modules["usb.core"] = core
    sys.modules["usb.util"] = util
    return USBError


def _drop_usb() -> None:
    for name in ("usb", "usb.core", "usb.util"):
        sys.modules.pop(name, None)


def test_open_rebinds_second_keyboard_without_detaching(monkeypatch: pytest.MonkeyPatch) -> None:
    dev = _FakeDev(active={0, 2})
    _install_usb(dev)
    monkeypatch.setattr(TartarusDevice, "_open_hidraw", lambda self: None)
    try:
        device = TartarusDevice()
        device.open()
        device.close()
    finally:
        _drop_usb()

    assert dev.detached == []
    assert dev.claimed == []
    assert 1 in dev.attached
    assert 0 in dev.active and 1 in dev.active and 2 in dev.active


def test_open_leaves_already_bound_keyboards_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    dev = _FakeDev(active={0, 1, 2})
    _install_usb(dev)
    monkeypatch.setattr(TartarusDevice, "_open_hidraw", lambda self: None)
    try:
        TartarusDevice().open()
    finally:
        _drop_usb()

    assert dev.detached == []
    assert dev.attached == []
    assert dev.claimed == []


def test_missing_keypad_still_raises() -> None:
    usb = ModuleType("usb")
    core = ModuleType("usb.core")
    util = ModuleType("usb.util")
    core.find = lambda **_kwargs: None
    util.dispose_resources = lambda _device: None
    usb.core = core
    usb.util = util
    sys.modules["usb"] = usb
    sys.modules["usb.core"] = core
    sys.modules["usb.util"] = util
    try:
        with pytest.raises(DeviceError, match="not found"):
            TartarusDevice().open()
    finally:
        _drop_usb()


def test_input_interfaces_include_both_keyboards() -> None:
    assert INPUT_INTERFACES == (0, 1, 2)


def test_hidraw_match_and_lookup(tmp_path) -> None:
    uevent = (
        "DRIVER=hid-generic\n"
        "HID_ID=0003:00001532:0000022B\n"
        "HID_PHYS=usb-0000:0c:00.3-3/input1\n"
    )
    assert hidraw_matches(uevent, vendor=0x1532, product=0x022B, interface=1)
    assert not hidraw_matches(uevent, vendor=0x1532, product=0x022B, interface=0)
    node = tmp_path / "hidraw6" / "device"
    node.mkdir(parents=True)
    (node / "uevent").write_text(uevent, encoding="utf-8")
    boot = tmp_path / "hidraw3" / "device"
    boot.mkdir(parents=True)
    (boot / "uevent").write_text(
        uevent.replace("input1", "input0"), encoding="utf-8"
    )
    assert find_tartarus_hidraw(1, root=tmp_path) == "/dev/hidraw6"
    assert find_tartarus_hidraw(2, root=tmp_path) is None
    assert hid_feature_ioctl(0x06, 91) == 0xC05B4806


def test_feature_report_roundtrip_skips_report_id() -> None:
    payload = bytes(range(90))
    packed = pack_feature_report(payload)
    assert packed[0] == 0
    assert bytes(packed[1:]) == payload
    assert unpack_feature_report(packed) == payload


def test_send_uses_hidraw_feature_report(monkeypatch: pytest.MonkeyPatch) -> None:
    import fcntl

    from tartarus_v2.hid import protocol

    device = TartarusDevice()
    device._fd = 4
    seen: list[tuple[int, bytes]] = []

    def fake_ioctl(_fd: int, request: int, buf: bytearray, mutate: bool = False) -> int:
        seen.append((request, bytes(buf)))
        if mutate and request == hid_feature_ioctl(0x07, len(buf)):
            reply = protocol.RazerReport(status=0x02, command_class=0x0F, command_id=0x02)
            raw = reply.to_bytes()
            buf[1 : 1 + len(raw)] = raw
        return 0

    monkeypatch.setattr(fcntl, "ioctl", fake_ioctl)
    monkeypatch.setattr("tartarus_v2.hid.device.time.sleep", lambda _s: None)
    report = protocol.effect_spectrum(0x01, 0x05)
    parsed = device.send(report)
    assert parsed.status == 0x02
    assert seen[0][0] == hid_feature_ioctl(0x06, 91)
    assert seen[0][1][0] == 0
    assert len(seen[0][1]) == 91


def test_node_lost_is_not_a_uinput_permissions_finding() -> None:
    text = """
2026-09-24T19:21:38.924 INFO tartarus_v2.remap: Creating virtual keyboard via /dev/uinput
2026-09-24T19:22:05.994 WARNING tartarus_v2.hid: Claimed alternate interface 0
2026-09-24T19:22:06.049 ERROR tartarus_v2.daemon: Remapper failed; keypad keys stay at firmware defaults: [Errno 19] No such device
"""
    findings = daemon_log_findings(text)
    joined = "\n".join(findings)
    assert "No such device" in joined or "ENODEV" in joined
    assert "not a /dev/uinput permission problem" in joined
    assert "fix-permissions" not in joined


def test_latest_session_explains_detached_second_keyboard() -> None:
    text = """
2026-09-24T20:27:47.404 ERROR tartarus_v2.daemon: Remapper failed; keypad keys stay at firmware defaults: [Errno 19] No such device
2026-09-24T20:37:15.451 INFO tartarus_v2.daemon: Starting daemon with profile=default
2026-09-24T20:37:15.581 INFO tartarus_v2.hid: Detached kernel driver from interface 1
2026-09-24T20:37:15.736 INFO tartarus_v2.remap: Remapper started (system-wide uinput); hypershift_key='mode' devices=2
"""
    findings = daemon_log_findings(text)
    joined = "\n".join(findings)
    assert "interface 1" in joined
    assert "diagnostic" in joined
    assert "No such device" not in joined


def test_uinput_failure_still_suggests_fix_permissions() -> None:
    text = (
        "ERROR tartarus_v2.daemon: Remapper failed; keypad keys stay at firmware defaults: "
        "Cannot create the virtual keyboard (/dev/uinput): permission denied."
    )
    findings = daemon_log_findings(text)
    assert any("fix-permissions" in line for line in findings)


def test_input_node_lost_message_mentions_no_keys() -> None:
    msg = input_node_lost_message(OSError(errno.ENODEV, "No such device"))
    assert "no keys" in msg
    assert "firmware defaults" in msg


def test_run_forever_reports_vanished_node(monkeypatch: pytest.MonkeyPatch) -> None:
    remapper = Remapper({})
    remapper._running = True
    remapper._ui = object()

    class Dev:
        fd = 7
        path = "/dev/input/event26"

        def read(self) -> None:
            raise OSError(errno.ENODEV, "No such device")

        def ungrab(self) -> None:
            return None

        def close(self) -> None:
            return None

    remapper._devices = [Dev()]
    monkeypatch.setattr(
        "tartarus_v2.input.remapper.select.select",
        lambda fds, *_a, **_k: (list(fds), [], []),
    )
    with pytest.raises(RuntimeError, match="no keys"):
        remapper.run_forever()


def test_device_info_and_effect_skip_usb_while_daemon_runs(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    daemon_control.pid_path().parent.mkdir(parents=True, exist_ok=True)
    daemon_control.pid_path().write_text(f"{os.getpid()}\n", encoding="utf-8")
    monkeypatch.setattr("tartarus_v2.daemon_control.os.kill", lambda *_a, **_k: None)

    from unittest.mock import patch

    with patch("tartarus_v2.hid.device.TartarusDevice") as dev:
        info = actions.device_info()
        actions.set_effect("static", rgb="112233", rgb2="445566", brightness=40)
        actions.set_brightness(90)
    dev.assert_not_called()
    assert "owns the keypad" in info["serial"]
    lighting = profiles.load_profile(profiles.get_active_profile_name())["lighting"]
    assert lighting["effect"] == "static"
    assert lighting["rgb"] == "112233"
    assert lighting["rgb2"] == "445566"
    assert lighting["brightness"] == 90


def test_live_probe_skips_when_daemon_running(monkeypatch: pytest.MonkeyPatch) -> None:
    from tartarus_v2.diagnose import _live_probe
    from tartarus_v2.daemon_control import DaemonStatus

    monkeypatch.setattr(
        "tartarus_v2.daemon_control.status",
        lambda: DaemonStatus(running=True, pid=42, detail="running"),
    )
    text = _live_probe()
    assert "skipped" in text
    assert "pid 42" in text
