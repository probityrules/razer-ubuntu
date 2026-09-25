"""Broader unit coverage for protocol, actions, daemon_control, logging, profiles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tartarus_v2.hid import protocol
from tartarus_v2.logging_util import annotate_report, hex_dump, log_path, setup_logging
from tartarus_v2 import actions, daemon_control, profiles
from tartarus_v2.gui.controllers import LightingController, AppController, DaemonController


def test_protocol_builders_and_crc() -> None:
    for builder in (
        lambda: protocol.effect_none(1, 5),
        lambda: protocol.effect_spectrum(1, 5),
        lambda: protocol.effect_wave(1, 5, 1),
        lambda: protocol.effect_static(1, 5, 1, 2, 3),
        lambda: protocol.effect_reactive(1, 5, 2, 1, 2, 3),
        lambda: protocol.effect_breath_random(1, 5),
        lambda: protocol.effect_breath_single(1, 5, 1, 2, 3),
        lambda: protocol.effect_breath_dual(1, 5, 1, 2, 3, 4, 5, 6),
        lambda: protocol.effect_starlight_random(1, 5, 2),
        lambda: protocol.effect_starlight_single(1, 5, 2, 1, 2, 3),
        lambda: protocol.effect_custom_frame(),
        lambda: protocol.set_custom_frame_row(0, 0, 1, bytes([1, 2, 3, 4, 5, 6])),
        lambda: protocol.set_brightness(1, 0, 100),
        lambda: protocol.get_brightness(1, 0),
        lambda: protocol.set_device_mode(3),
        lambda: protocol.get_device_mode(),
        lambda: protocol.get_serial(),
        lambda: protocol.set_led_state(1, 7, True),
        lambda: protocol.get_led_state(1, 7),
    ):
        report = builder()
        report.transaction_id = 0x1F
        raw = report.to_bytes()
        assert len(raw) == 90
        assert protocol.RazerReport.from_bytes(raw).command_class == report.command_class


def test_logging_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    setup_logging(debug=True)
    assert log_path().exists() or log_path().parent.exists()
    data = bytes(range(32))
    assert "0000:" in hex_dump(data)
    report = protocol.get_firmware_version()
    report.transaction_id = 0x1F
    text = annotate_report(report.to_bytes())
    assert "status=" in text
    assert "short report" in annotate_report(b"\x00\x01")


def test_actions_set_effect_invalid() -> None:
    with pytest.raises(ValueError):
        actions.set_effect("nope")


def test_actions_save_bindings_invalid_layer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        actions.save_bindings("default", "nope", {})


@patch("tartarus_v2.hid.chroma.ChromaController")
@patch("tartarus_v2.hid.device.TartarusDevice")
def test_device_info_and_effects(
    mock_dev: MagicMock,
    mock_chroma_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    profiles.ensure_default_profile()
    mock_dev.return_value.__enter__.return_value = MagicMock()
    chroma = MagicMock()
    chroma.get_firmware.return_value = "v1.0"
    chroma.get_serial.return_value = "SN"
    chroma.get_brightness.return_value = 42
    mock_chroma_cls.return_value = chroma

    info = actions.device_info()
    assert info["firmware"] == "v1.0"
    actions.set_brightness(10)
    assert profiles.load_profile("default")["lighting"]["brightness"] == 10
    for effect in actions.LIGHTING_EFFECTS:
        actions.set_effect(effect, rgb="FF0000", rgb2="00FF00")
    assert profiles.load_profile("default")["lighting"]["rgb"] == "FF0000"


def test_lighting_persists_without_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    profiles.ensure_default_profile()
    with patch("tartarus_v2.hid.device.TartarusDevice") as mock_dev:
        mock_dev.return_value.__enter__.return_value = MagicMock()
        with patch("tartarus_v2.hid.chroma.ChromaController"):
            saved = actions.set_effect(
                "static", rgb="AABBCC", brightness=50, profile_name="default"
            )
    assert saved == "default"
    data = profiles.load_profile("default")
    assert data["lighting"]["effect"] == "static"
    assert data["lighting"]["rgb"] == "AABBCC"
    assert data["lighting"]["brightness"] == 50


def test_lighting_persists_with_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    profiles.ensure_default_profile()
    monkeypatch.setattr(
        "tartarus_v2.actions._running_daemon",
        lambda: type("S", (), {"running": True, "pid": 1})(),
    )
    with patch("tartarus_v2.actions.nudge_daemon_reload", return_value="reloaded") as nudge:
        with patch("tartarus_v2.hid.device.TartarusDevice") as mock_dev:
            saved = actions.set_effect("static", rgb="112233", brightness=40)
    assert saved == "default"
    nudge.assert_called_once()
    mock_dev.assert_not_called()
    lighting = profiles.load_profile("default")["lighting"]
    assert lighting["rgb"] == "112233"
    assert lighting["brightness"] == 40


def test_lighting_controller_forwards_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with patch("tartarus_v2.gui.controllers.actions.set_effect", return_value="default") as mock_set:
        out = LightingController().apply_effect(
            "static", rgb="AABBCC", brightness=50, profile_name="default"
        )
    assert out == "default"
    mock_set.assert_called_once()
    assert mock_set.call_args.kwargs["profile_name"] == "default"
    assert mock_set.call_args.kwargs["rgb"] == "AABBCC"


def test_use_profile_applies_lighting_without_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    profiles.ensure_default_profile()
    other = profiles.load_profile("default")
    other["lighting"] = {"effect": "static", "rgb": "FF00AA", "brightness": 80}
    profiles.save_profile(other, "red")
    profiles.set_active_profile_name("default")

    chroma = MagicMock()
    with patch("tartarus_v2.actions._running_daemon", return_value=None):
        with patch("tartarus_v2.hid.device.TartarusDevice") as mock_dev:
            mock_dev.return_value.__enter__.return_value = MagicMock()
            with patch(
                "tartarus_v2.hid.chroma.ChromaController", return_value=chroma
            ):
                assert actions.use_profile("red") == "red"

    assert profiles.get_active_profile_name() == "red"
    chroma.apply_lighting.assert_called_once_with(
        {"effect": "static", "rgb": "FF00AA", "brightness": 80}
    )


def test_use_profile_reloads_daemon_when_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    profiles.ensure_default_profile()
    profiles.save_profile(profiles.load_profile("default"), "second")
    monkeypatch.setattr(
        "tartarus_v2.actions._running_daemon",
        lambda: type("S", (), {"running": True, "pid": 9})(),
    )
    with patch("tartarus_v2.actions.nudge_daemon_reload", return_value="reload signaled") as nudge:
        with patch("tartarus_v2.hid.device.TartarusDevice") as mock_dev:
            assert actions.use_profile("second") == "second"
    nudge.assert_called_once()
    mock_dev.assert_not_called()
    assert profiles.get_active_profile_name() == "second"


def test_cycle_active_profile_applies_lighting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    profiles.ensure_default_profile()
    second = profiles.load_profile("default")
    second["lighting"] = {"effect": "wave", "direction": 1, "brightness": 40}
    profiles.save_profile(second, "second")
    profiles.set_active_profile_name("default")
    chroma = MagicMock()
    with patch("tartarus_v2.actions._running_daemon", return_value=None):
        with patch("tartarus_v2.hid.device.TartarusDevice") as mock_dev:
            mock_dev.return_value.__enter__.return_value = MagicMock()
            with patch(
                "tartarus_v2.hid.chroma.ChromaController", return_value=chroma
            ):
                assert actions.cycle_active_profile("next") == "second"
    assert profiles.get_active_profile_name() == "second"
    chroma.apply_lighting.assert_called_once()


def test_profile_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    profiles.ensure_default_profile()
    profiles.save_profile(profiles.load_profile("default"), "second")
    profiles.set_active_profile_name("default")
    assert profiles.cycle_profile("next") == "second"
    assert profiles.cycle_profile("prev") == "default"


def test_daemon_control_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert not daemon_control.stop().running
    daemon_control.pid_path().write_text("not-a-pid\n", encoding="utf-8")
    assert daemon_control._read_pid() is None
    daemon_control.pid_path().write_text("999999\n", encoding="utf-8")
    with patch("tartarus_v2.daemon_control._pid_alive", return_value=False):
        st = daemon_control.status()
        assert not st.running

    proc = MagicMock(pid=7, poll=MagicMock(return_value=1), returncode=1)
    with patch("tartarus_v2.daemon_control.subprocess.Popen", return_value=proc):
        st = daemon_control.start()
        assert not st.running

    with patch("tartarus_v2.daemon_control.status") as mock_status:
        mock_status.return_value = daemon_control.DaemonStatus(running=True, pid=1)
        # already running
        with patch("tartarus_v2.daemon_control.subprocess.Popen") as popen:
            # start checks status first
            pass
    # re-test already running path properly
    with patch(
        "tartarus_v2.daemon_control.status",
        return_value=daemon_control.DaemonStatus(running=True, pid=99, detail="running"),
    ):
        st = daemon_control.start()
        assert st.detail == "already running"


def test_daemon_kill_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    daemon_control.pid_path().parent.mkdir(parents=True, exist_ok=True)
    daemon_control.pid_path().write_text("55\n", encoding="utf-8")
    with patch("tartarus_v2.daemon_control.systemd_unit_enabled", return_value=False):
        with patch("tartarus_v2.daemon_control.systemd_unit_active", return_value=False):
            with patch("tartarus_v2.daemon_control._pid_alive", return_value=True):
                with patch("tartarus_v2.daemon_control.os.kill") as kill:
                    with patch("tartarus_v2.daemon_control.time.sleep"):
                        with patch(
                            "tartarus_v2.daemon_control.time.time",
                            side_effect=[0, 10, 10],
                        ):
                            st = daemon_control.stop(timeout=0.01)
                            assert not st.running
                            assert kill.call_count >= 1


@patch("tartarus_v2.actions.launch_gui", return_value=0)
def test_app_controller(mock_launch: MagicMock) -> None:
    # AppController.launch calls actions.launch_gui
    with patch("tartarus_v2.gui.controllers.actions.launch_gui", return_value=0) as m:
        assert AppController().launch() == 0
        m.assert_called_once()


def test_create_profile_and_uninstall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    path = actions.create_profile("newbie")
    assert path.exists()
    with pytest.raises(ValueError):
        actions.create_profile("newbie")
    with pytest.raises(ValueError):
        actions.create_profile("  ")

    with patch("tartarus_v2.daemon_control.stop"):
        with patch("shutil.which", return_value=None):
            msg = actions.uninstall_package()
            assert "apt-get not found" in msg

    with patch("tartarus_v2.daemon_control.stop"):
        with patch(
            "shutil.which",
            side_effect=lambda c: "/usr/bin/apt-get" if c == "apt-get" else None,
        ):
            msg = actions.uninstall_package()
            assert "pkexec" in msg or "sudo" in msg

    fake = MagicMock(returncode=0, stdout="", stderr="")
    with patch("tartarus_v2.daemon_control.stop"):
        with patch("shutil.which", return_value="/usr/bin/x"):
            with patch("subprocess.run", return_value=fake) as run:
                msg = actions.uninstall_package()
                assert "removed" in msg
                assert run.called


def test_start_daemon_background() -> None:
    with patch(
        "tartarus_v2.daemon_control.start",
        return_value=daemon_control.DaemonStatus(running=True, pid=3, detail="started"),
    ) as start:
        st = actions.start_daemon_background(profile="default", debug=True)
        assert st.running
        start.assert_called_once_with(profile="default", debug=True)


def test_short_label_keys() -> None:
    from tartarus_v2.input.keys import (
        ALL_LOGICAL_KEYS,
        KEYMAP_LAYOUT,
        KEYMAP_PAD_LAYOUT,
        KEYMAP_SCROLL_COLUMN,
        LOGICAL_TO_CODE,
        describe_logical,
        short_label,
    )

    assert short_label("stick_up") == "↑"
    assert short_label("key_01") == "01"
    assert short_label("mode") == "mode"
    assert short_label("key_20") == "20"
    assert short_label("thumb") == "20"
    assert describe_logical("key_20") == "key 20 (thumb)"
    assert describe_logical("thumb") == "key 20 (thumb)"
    assert short_label("custom") == "custom"
    flat = {k for row in KEYMAP_LAYOUT for k in row if k}
    for n in range(1, 20):
        assert f"key_{n:02d}" in flat
    assert "key_20" in flat
    assert "thumb" not in flat
    assert "scroll_up" in flat
    assert "mode" in flat
    # Bottom keypad row is keys 16–19. Key 20 is the thumb, not a fifth key.
    assert KEYMAP_LAYOUT[3] == ["key_16", "key_17", "key_18", "key_19"]
    assert KEYMAP_PAD_LAYOUT[3] == ["key_16", "key_17", "key_18", "key_19"]
    assert KEYMAP_SCROLL_COLUMN == ["scroll_up", "scroll_click", "scroll_down"]
    assert "key_20" not in KEYMAP_LAYOUT[3]
    assert all(key is not None for key in KEYMAP_LAYOUT[3])
    assert LOGICAL_TO_CODE["key_20"] == 57
    assert "thumb" not in LOGICAL_TO_CODE
    assert "thumb" not in ALL_LOGICAL_KEYS
    assert "key_20" in ALL_LOGICAL_KEYS
    assert describe_logical("mode") == "mode"

    from tartarus_v2.input.keys import fold_thumb_alias, lookup_binding

    assert lookup_binding([], "key_20") is None  # type: ignore[arg-type]
    both = {"key_20": "n", "thumb": "space"}
    assert lookup_binding(both, "key_20") == "space"
    assert lookup_binding({"key_01": "a"}, "key_01") == "a"
    assert lookup_binding({"thumb": "space"}, "missing") is None

    bare = {"hypershift_key": 1, "standard": "nope", "hypershift": {"bindings": []}}
    fold_thumb_alias(bare)  # type: ignore[arg-type]
    assert bare["hypershift_key"] == 1

    from tartarus_v2.input.keys import strip_hypershift_key_bindings

    cleaned = strip_hypershift_key_bindings(
        {"mode": "x", "key_01": "1", "thumb": "space"},
        "mode",
    )
    assert "mode" not in cleaned
    assert cleaned["key_01"] == "1"
    assert strip_hypershift_key_bindings({"key_20": "a", "thumb": "b"}, "key_20") == {}

    from tartarus_v2.input.keys import (
        binding_picker_choices,
        binding_source_kind,
        format_binding_for_entry,
        parse_binding_from_entry,
        validate_binding_text,
    )

    assert binding_source_kind("scroll_up") == "scroll"
    assert binding_source_kind("key_01") == "key"
    key_choices = binding_picker_choices(kind="key")
    assert key_choices[0] == ("Insert…", None)
    assert ("Clear binding", "") in key_choices
    assert ("ctrl", "ctrl") in key_choices
    assert ("F1", "F1") in key_choices
    assert ("ctrl+c", "ctrl+c") in key_choices
    assert ("Profile next", "profile_next") in key_choices
    assert ("Mouse wheel up", "scroll_up") not in key_choices
    scroll_choices = binding_picker_choices(kind="scroll")
    assert ("Mouse wheel up", "scroll_up") in scroll_choices
    assert ("Mouse wheel left", "scroll_left") in scroll_choices
    assert ("a", "a") not in scroll_choices
    assert parse_binding_from_entry("") is None
    assert parse_binding_from_entry("  ctrl+c ") == "ctrl+c"
    assert parse_binding_from_entry("profile_next") == {"type": "profile_next"}
    assert parse_binding_from_entry("PROFILE_PREV") == {"type": "profile_prev"}
    assert parse_binding_from_entry("scroll_left") == "scroll_left"
    assert format_binding_for_entry({"type": "profile_next"}) == "profile_next"
    assert format_binding_for_entry("a") == "a"
    assert format_binding_for_entry({"type": "macro", "steps": [{"tap": "ctrl+v"}]}) == "ctrl+v"
    assert validate_binding_text("scroll_left", source_kind="key")
    assert validate_binding_text("scroll_left", source_kind="scroll") is None
    assert validate_binding_text("ctrl+c", source_kind="key") is None
    assert validate_binding_text("profile_next", source_kind="scroll") is None


def test_remapper_skips_virtual_keyboard_device() -> None:
    from types import SimpleNamespace

    from tartarus_v2.input.remapper import Remapper

    assert Remapper._is_physical_tartarus(  # noqa: SLF001
        SimpleNamespace(name="Razer Tartarus V2")
    )
    assert not Remapper._is_physical_tartarus(  # noqa: SLF001
        SimpleNamespace(name="Tartarus V2 Virtual Keyboard")
    )
    assert not Remapper._is_physical_tartarus(  # noqa: SLF001
        SimpleNamespace(name="Some Other Keyboard")
    )
    from tartarus_v2 import key_listen

    profile = {
        "hypershift_key": "mode",
        "standard": {"bindings": {"key_14": "r", "key_01": "1"}},
        "hypershift": {"bindings": {"key_14": "F16"}},
    }
    # Without real evdev KEY_* attrs this may be empty on some hosts; still must not crash.
    result = key_listen.logicals_for_output_code(profile, 19, hypershift=False)
    assert isinstance(result, list)


def test_key_listen_describe_and_format() -> None:
    from tartarus_v2 import key_listen

    profile = {
        "name": "default",
        "hypershift_key": "mode",
        "standard": {"bindings": {"key_02": "w", "key_16": "ctrl"}},
        "hypershift": {"bindings": {"key_02": "F2"}},
    }
    # Physical key 02 emits KEY_2 (code 3).
    line = key_listen.describe_press(
        3, pressed=True, profile=profile, hypershift_held=False, ecodes=None
    )
    assert line.logical == "key_02"
    assert line.mapping == "w"
    assert "DOWN" in key_listen.format_key_line(line)

    hs = key_listen.describe_press(
        3, pressed=True, profile=profile, hypershift_held=True, ecodes=None
    )
    assert hs.mapping == "F2"
    assert key_listen.format_binding({"type": "macro", "steps": [{"tap": "a"}]}) == "macro(a)"
    assert key_listen.format_binding(None) == "(no mapping)"

    unknown = key_listen.describe_press(
        9999, pressed=True, profile=profile, hypershift_held=False, ecodes=None
    )
    assert unknown.logical == "?"
    assert "LOGICAL_TO_CODE" in unknown.mapping

    virt = key_listen.describe_virtual_press(
        17, pressed=True, profile=profile, hypershift_held=False, ecodes=None
    )
    assert virt.pressed
    assert "virtual" in virt.mapping


def test_evdev_key_calibration_matches_hardware() -> None:
    """Physical EV_KEY codes from live evtest on Tartarus V2."""
    from tartarus_v2.input.keys import CODE_TO_LOGICAL, LOGICAL_TO_CODE

    expected = {
        "key_01": 2,
        "key_02": 3,
        "key_03": 4,
        "key_04": 5,
        "key_05": 6,
        "key_06": 15,
        "key_07": 16,
        "key_08": 17,
        "key_09": 18,
        "key_10": 19,
        "key_11": 58,
        "key_12": 30,
        "key_13": 31,
        "key_14": 32,
        "key_15": 33,
        "key_16": 42,
        "key_17": 44,
        "key_18": 45,
        "key_19": 46,
        "key_20": 57,
        "mode": 56,
        "stick_left": 105,
        "stick_up": 103,
        "stick_right": 106,
        "stick_down": 108,
    }
    for logical, code in expected.items():
        assert LOGICAL_TO_CODE[logical] == code, logical
        assert CODE_TO_LOGICAL[code] == logical, code


def test_session_groups_ignore_database_until_relogin(monkeypatch: pytest.MonkeyPatch) -> None:
    from tartarus_v2 import permissions

    monkeypatch.setattr(permissions, "current_username", lambda: "alice")
    monkeypatch.setattr(permissions, "session_group_names", lambda: {"users"})
    monkeypatch.setattr(
        permissions,
        "database_group_names",
        lambda _u: {"users", "input", "plugdev"},
    )
    monkeypatch.setattr(permissions, "uinput_status", lambda: (False, "/dev/uinput is not writable"))
    assert permissions.user_group_names() == {"users"}
    st = permissions.permission_status()
    assert st.needs_relogin
    assert not st.ok
    assert "Log out" in st.detail
    assert "root" in st.detail


def test_uinput_status_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    from tartarus_v2 import permissions

    monkeypatch.setattr(permissions.os.path, "exists", lambda _p: False)
    ok, detail = permissions.uinput_status()
    assert not ok
    assert "missing" in detail

    monkeypatch.setattr(permissions.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(permissions.os, "access", lambda _p, _m: True)
    ok, detail = permissions.uinput_status()
    assert ok
    assert "writable" in detail

    monkeypatch.setattr(permissions.os, "access", lambda _p, _m: False)
    ok, detail = permissions.uinput_status()
    assert not ok
    assert "not writable" in detail


def test_permissions_status_and_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    from tartarus_v2 import permissions
    from tartarus_v2.permissions import PermissionStatus

    monkeypatch.setattr(permissions, "current_username", lambda: "alice")
    monkeypatch.setattr(permissions, "user_group_names", lambda _u=None: {"users", "plugdev"})
    st = permissions.permission_status()
    assert not st.ok
    assert "input" in st.missing

    monkeypatch.setattr(permissions, "user_group_names", lambda _u=None: {"input", "plugdev"})
    monkeypatch.setattr(permissions, "uinput_status", lambda: (True, "/dev/uinput is writable"))
    assert permissions.permission_status().ok
    monkeypatch.setattr(permissions, "uinput_status", lambda: (False, "/dev/uinput is not writable"))
    denied = permissions.permission_status()
    assert not denied.ok
    assert "uinput" in denied.detail

    monkeypatch.setattr(
        permissions,
        "permission_status",
        lambda username=None: PermissionStatus(
            user="alice",
            groups=("input", "plugdev"),
            missing=(),
            ok=True,
            detail="ok",
        ),
    )
    assert "already" in permissions.fix_permissions().lower()

    monkeypatch.setattr(
        permissions,
        "permission_status",
        lambda username=None: PermissionStatus(
            user="alice",
            groups=("plugdev",),
            missing=("input",),
            ok=False,
            detail="missing",
        ),
    )
    monkeypatch.setattr(
        permissions.shutil, "which", lambda c: "/usr/bin/pkexec" if c == "pkexec" else None
    )
    fake = MagicMock(returncode=0, stdout="", stderr="")
    with patch("tartarus_v2.permissions.subprocess.run", return_value=fake) as run:
        msg = permissions.fix_permissions()
        assert "Log out" in msg or "log out" in msg.lower()
        assert run.called

    with patch(
        "tartarus_v2.gui.controllers.actions.permission_status",
        return_value=PermissionStatus(
            user="alice", groups=("input", "plugdev"), missing=(), ok=True, detail="ok"
        ),
    ):
        assert DaemonController().permission_status().ok
    with patch("tartarus_v2.gui.controllers.actions.fix_permissions", return_value="fixed") as m:
        assert DaemonController().fix_permissions() == "fixed"
        m.assert_called_once()


def test_app_controller_uninstall() -> None:
    with patch("tartarus_v2.gui.controllers.actions.uninstall_package", return_value="ok") as m:
        assert AppController().uninstall() == "ok"
        m.assert_called_once()


def test_actions_permission_wrappers() -> None:
    from tartarus_v2.permissions import PermissionStatus

    fake = PermissionStatus(
        user="bob", groups=("input", "plugdev"), missing=(), ok=True, detail="ok"
    )
    with patch("tartarus_v2.permissions.permission_status", return_value=fake):
        assert actions.permission_status().ok
    with patch("tartarus_v2.permissions.fix_permissions", return_value="done"):
        assert actions.fix_permissions() == "done"


def test_permissions_root_and_missing_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from tartarus_v2 import permissions
    from tartarus_v2.permissions import PermissionStatus

    monkeypatch.setattr(
        permissions,
        "permission_status",
        lambda username=None: PermissionStatus(
            user="root", groups=(), missing=("input", "plugdev"), ok=False, detail="x"
        ),
    )
    assert "Cannot fix" in permissions.fix_permissions()

    monkeypatch.setattr(
        permissions,
        "permission_status",
        lambda username=None: PermissionStatus(
            user="carol",
            groups=(),
            missing=("input",),
            ok=False,
            detail="missing",
        ),
    )
    monkeypatch.setattr(permissions.shutil, "which", lambda _c: None)
    msg = permissions.fix_permissions()
    assert "pkexec/sudo not found" in msg

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):  # noqa: ANN001
        calls.append(list(cmd))
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("tartarus_v2.permissions.subprocess.run", side_effect=fake_run):
        msg = permissions._apply_as_root("carol")
        assert "Log out" in msg or "log out" in msg.lower()
        assert calls and calls[0][0] == "sh"
        script = calls[0][2]
        assert "usermod" in script
        assert "modprobe uinput" in script


def test_features_collect_empty() -> None:
    from tartarus_v2.features import collect_argparse_commands
    import argparse

    p = argparse.ArgumentParser()
    assert collect_argparse_commands(p) == set()
