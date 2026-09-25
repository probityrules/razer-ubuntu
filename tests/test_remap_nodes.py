"""Which Tartarus evdev nodes the remapper must grab."""

from __future__ import annotations

import errno

from tartarus_v2.input.remapper import (
    Remapper,
    grab_error_is_fatal,
    input_index_from_phys,
    is_tartarus_event_node,
    mirror_duplicate,
    uinput_failure_message,
    virtual_keyboard_keycodes,
    waiting_for_second_keyboard,
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
    # BTN_DPAD_* and BTN_TRIGGER_HAPPY* are joystick buttons past KEY_OK.
    assert 0x220 not in codes
    assert 0x223 not in codes
    assert 0x2C0 not in codes
    assert 0x2E7 not in codes
    assert 0x21F in codes  # last key before BTN_DPAD_UP
    assert 0x230 in codes  # KEY_ALS_TOGGLE, after the d-pad gap


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


def test_input_index_from_phys() -> None:
    assert input_index_from_phys("usb-0000:0c:00.3-3/input0") == 0
    assert input_index_from_phys("usb-0000:0c:00.3-3/input1") == 1
    assert input_index_from_phys("usb-0000:0c:00.3-3/input2") == 2
    assert input_index_from_phys("py-evdev-uinput") is None
    assert input_index_from_phys("") is None


def test_mirror_duplicate_drops_only_the_echo() -> None:
    seen: dict[tuple[int, int], tuple[float, int]] = {}
    assert not mirror_duplicate(seen, source=1, code=2, value=1, now=1.0)
    assert mirror_duplicate(seen, source=0, code=2, value=1, now=1.01)
    # Same interface, later press, is a real repeat.
    assert not mirror_duplicate(seen, source=1, code=2, value=1, now=1.2)
    # Mouse wheel interface is not part of the keyboard mirror.
    assert not mirror_duplicate(seen, source=2, code=2, value=1, now=1.21)
    # Release on the other interface after the window is a real event.
    assert not mirror_duplicate(seen, source=0, code=2, value=0, now=2.0)
    assert not mirror_duplicate(seen, source=1, code=2, value=0, now=2.1)


def test_wait_until_second_keyboard_appears(monkeypatch) -> None:
    class Node:
        def __init__(self, phys: str) -> None:
            self.phys = phys
            self.closed = False

        def close(self) -> None:
            self.closed = True

    boot = Node("usb-1/input0")
    mouse = Node("usb-1/input2")
    nkro = Node("usb-1/input1")
    assert waiting_for_second_keyboard([boot, mouse], now=0.0, grace_deadline=2.0)
    assert not waiting_for_second_keyboard([boot, nkro], now=0.0, grace_deadline=2.0)
    assert not waiting_for_second_keyboard([boot], now=2.0, grace_deadline=2.0)
    assert not waiting_for_second_keyboard(["dev"], now=0.0, grace_deadline=2.0)

    remapper = Remapper({})
    calls = {"n": 0}

    def fake_find() -> list[Node]:
        calls["n"] += 1
        if calls["n"] == 1:
            return [boot, mouse]
        return [boot, mouse, nkro]

    monkeypatch.setattr(remapper, "find_devices", fake_find)
    monkeypatch.setattr("tartarus_v2.input.remapper.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "tartarus_v2.input.remapper.time.monotonic",
        lambda: 0.0 if calls["n"] < 2 else 0.2,
    )
    found = remapper.find_devices_retry(timeout=5)
    assert nkro in found
    assert boot.closed  # first batch is closed while waiting for input1


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


def test_unknown_key_token_does_not_raise() -> None:
    from types import SimpleNamespace

    remapper = Remapper({})
    remapper._ecodes = SimpleNamespace(KEY_A=30)  # noqa: SLF001
    assert remapper.resolve_key_token("scroll_left") == []
    assert remapper.resolve_key_token("not_a_real_key_zzzz") == []
    assert remapper.resolve_key_token("a") == [30]


def test_wheel_binding_emits_rel_not_key() -> None:
    from types import SimpleNamespace

    remapper = Remapper({})
    remapper._ecodes = SimpleNamespace(  # noqa: SLF001
        EV_REL=2,
        REL_WHEEL=8,
        REL_HWHEEL=6,
        KEY_A=30,
    )
    writes: list[tuple[int, int, int]] = []

    class FakeUI:
        def write(self, etype: int, code: int, value: int) -> None:
            writes.append((etype, code, value))

        def syn(self) -> None:
            pass

    remapper._ui = FakeUI()  # noqa: SLF001
    remapper._logged_output = False  # noqa: SLF001
    remapper._apply_binding("scroll_left", True)  # noqa: SLF001
    remapper._apply_binding("scroll_right", True)  # noqa: SLF001
    remapper._apply_binding("scroll_up", True)  # noqa: SLF001
    assert writes == [
        (2, 6, -1),
        (2, 6, 1),
        (2, 8, 1),
    ]
    # Unknown keyboard token must not raise.
    remapper._apply_binding("scroll_left_typo", True)  # noqa: SLF001
