"""Which Tartarus evdev nodes the remapper must grab."""

from __future__ import annotations

import errno

from tartarus_v2.input.remapper import (
    grab_error_is_fatal,
    is_tartarus_event_node,
    uinput_failure_message,
)


def test_event_if01_is_grabbed_and_hidraw_is_not() -> None:
    names = [
        "usb-Razer_Razer_Tartarus_V2-event-if01",
        "usb-Razer_Razer_Tartarus_V2-event-kbd",
        "usb-Razer_Razer_Tartarus_V2-if01-event-kbd",
        "usb-Razer_Razer_Tartarus_V2-if02-event-mouse",
        "usb-Razer_Razer_Tartarus_V2-hidraw",
        "usb-Razer_Razer_Tartarus_V2-if01-hidraw",
        "usb-Razer_Razer_Tartarus_V2-if02-mouse",
        "usb-Tartarus_V2_Virtual_Keyboard-event-kbd",
    ]
    selected = [n for n in names if is_tartarus_event_node(n)]
    assert "usb-Razer_Razer_Tartarus_V2-event-if01" in selected
    assert "usb-Razer_Razer_Tartarus_V2-event-kbd" in selected
    assert "usb-Razer_Razer_Tartarus_V2-if01-event-kbd" in selected
    assert "usb-Razer_Razer_Tartarus_V2-if02-event-mouse" in selected
    assert "usb-Razer_Razer_Tartarus_V2-hidraw" not in selected
    assert "usb-Razer_Razer_Tartarus_V2-if02-mouse" not in selected
    assert "usb-Tartarus_V2_Virtual_Keyboard-event-kbd" not in selected


def test_grab_error_skips_vanished_nodes() -> None:
    assert not grab_error_is_fatal(OSError(errno.ENODEV, "no such device"))
    assert not grab_error_is_fatal(OSError(errno.ENOENT, "missing"))
    assert grab_error_is_fatal(OSError(errno.EACCES, "denied"))
    assert grab_error_is_fatal(OSError(errno.EBUSY, "busy"))


def test_uinput_failure_explains_default_keys() -> None:
    denied = uinput_failure_message(OSError(errno.EACCES, "denied"))
    assert "/dev/uinput" in denied
    assert "default keys" in denied
    assert "not required" in denied
    missing = uinput_failure_message(OSError(errno.ENOENT, "missing"))
    assert "missing" in missing
    other = uinput_failure_message(OSError(errno.EINVAL, "bad"))
    assert "/dev/uinput" in other
