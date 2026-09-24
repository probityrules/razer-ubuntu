"""Which Tartarus evdev nodes the remapper must grab."""

from __future__ import annotations

import errno

from tartarus_v2.input.remapper import (
    Remapper,
    grab_error_is_fatal,
    is_tartarus_event_node,
    uinput_failure_message,
    virtual_keyboard_keycodes,
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


def test_virtual_keyboard_excludes_joystick_buttons() -> None:
    codes = virtual_keyboard_keycodes(0x2FF)
    assert 2 in codes  # KEY_1
    assert 30 in codes  # KEY_A
    assert 57 in codes  # KEY_SPACE
    # BTN_MOUSE, BTN_JOYSTICK, BTN_GAMEPAD sit in the gap udev treats as a joystick.
    assert 0x110 not in codes
    assert 0x120 not in codes
    assert 0x130 not in codes
    assert 0x100 not in codes
    assert 0x160 in codes  # KEY_OK, past the button gap


def test_unmapped_key_is_passed_through() -> None:
    remapper = Remapper({})
    emitted: list[tuple[int, bool]] = []
    remapper._emit = lambda codes, pressed: emitted.append((codes[0], pressed))  # type: ignore[method-assign]

    class Event:
        def __init__(self, code: int, value: int) -> None:
            self.type = 1  # EV_KEY
            self.code = code
            self.value = value

    # evdev may be absent; the helper imports it. Skip the call shape by
    # patching only if import works — the constant EV_KEY is 1 either way.
    import sys
    from types import ModuleType

    evdev = ModuleType("evdev")
    ecodes = ModuleType("evdev.ecodes")
    ecodes.EV_KEY = 1
    evdev.ecodes = ecodes
    sys.modules["evdev"] = evdev
    sys.modules["evdev.ecodes"] = ecodes
    try:
        remapper._passthrough_unmapped(Event(99, 1))
        remapper._passthrough_unmapped(Event(99, 0))
        remapper._passthrough_unmapped(Event(99, 2))  # repeat ignored
    finally:
        sys.modules.pop("evdev", None)
        sys.modules.pop("evdev.ecodes", None)

    assert emitted == [(99, True), (99, False)]


def test_find_devices_retry_returns_when_keypad_appears(monkeypatch) -> None:
    remapper = Remapper({})
    calls = {"n": 0}

    def fake_find() -> list[str]:
        calls["n"] += 1
        if calls["n"] < 3:
            return []
        return ["dev"]

    monkeypatch.setattr(remapper, "find_devices", fake_find)
    monkeypatch.setattr("tartarus_v2.input.remapper.time.sleep", lambda _s: None)
    assert remapper.find_devices_retry(timeout=5) == ["dev"]
    assert calls["n"] == 3


def test_uinput_failure_explains_default_keys() -> None:
    denied = uinput_failure_message(OSError(errno.EACCES, "denied"))
    assert "/dev/uinput" in denied
    assert "default keys" in denied
    assert "not required" in denied
    missing = uinput_failure_message(OSError(errno.ENOENT, "missing"))
    assert "missing" in missing
    other = uinput_failure_message(OSError(errno.EINVAL, "bad"))
    assert "/dev/uinput" in other
