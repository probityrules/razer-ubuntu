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
def test_device_info_and_effects(mock_dev: MagicMock, mock_chroma_cls: MagicMock) -> None:
    mock_dev.return_value.__enter__.return_value = MagicMock()
    chroma = MagicMock()
    chroma.get_firmware.return_value = "v1.0"
    chroma.get_serial.return_value = "SN"
    chroma.get_brightness.return_value = 42
    mock_chroma_cls.return_value = chroma

    info = actions.device_info()
    assert info["firmware"] == "v1.0"
    actions.set_brightness(10)
    for effect in actions.LIGHTING_EFFECTS:
        actions.set_effect(effect, rgb="FF0000", rgb2="00FF00")


def test_lighting_save_to_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with patch("tartarus_v2.gui.controllers.actions.set_effect"):
        LightingController().apply_effect(
            "static", rgb="AABBCC", brightness=50, save_to_profile=True, profile_name="default"
        )
    data = profiles.load_profile("default")
    assert data["lighting"]["effect"] == "static"
    assert data["lighting"]["brightness"] == 50


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
    with patch(
        "tartarus_v2.daemon_control.status",
        return_value=daemon_control.DaemonStatus(running=True, pid=55),
    ):
        with patch("tartarus_v2.daemon_control._pid_alive", return_value=True):
            with patch("tartarus_v2.daemon_control.os.kill") as kill:
                with patch("tartarus_v2.daemon_control.time.sleep"):
                    with patch("tartarus_v2.daemon_control.time.time", side_effect=[0, 10, 10]):
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
    from tartarus_v2.input.keys import KEYMAP_LAYOUT, short_label

    assert short_label("stick_up") == "↑"
    assert short_label("key_01") == "01"
    assert short_label("mode") == "mode"
    assert short_label("custom") == "custom"
    flat = {k for row in KEYMAP_LAYOUT for k in row if k}
    for n in range(1, 21):
        assert f"key_{n:02d}" in flat


def test_key_listen_describe_and_format() -> None:
    from tartarus_v2 import key_listen

    profile = {
        "name": "default",
        "hypershift_key": "mode",
        "standard": {"bindings": {"key_02": "w", "key_16": "ctrl"}},
        "hypershift": {"bindings": {"key_02": "F2"}},
    }
    line = key_listen.describe_press(
        16, pressed=True, profile=profile, hypershift_held=False, ecodes=None
    )
    assert line.logical == "key_02"
    assert line.mapping == "w"
    assert "DOWN" in key_listen.format_key_line(line)

    hs = key_listen.describe_press(
        16, pressed=True, profile=profile, hypershift_held=True, ecodes=None
    )
    assert hs.mapping == "F2"
    assert key_listen.format_binding({"type": "macro", "steps": [{"tap": "a"}]}) == "macro(a)"
    assert key_listen.format_binding(None) == "(no mapping)"

    unknown = key_listen.describe_press(
        9999, pressed=True, profile=profile, hypershift_held=False, ecodes=None
    )
    assert unknown.logical == "?"
    assert "LOGICAL_TO_CODE" in unknown.mapping


def test_permissions_status_and_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    from tartarus_v2 import permissions
    from tartarus_v2.permissions import PermissionStatus

    monkeypatch.setattr(permissions, "current_username", lambda: "alice")
    monkeypatch.setattr(permissions, "user_group_names", lambda _u=None: {"users", "plugdev"})
    st = permissions.permission_status()
    assert not st.ok
    assert "input" in st.missing

    monkeypatch.setattr(permissions, "user_group_names", lambda _u=None: {"input", "plugdev"})
    assert permissions.permission_status().ok

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
        assert any(c[0] == "usermod" for c in calls)


def test_features_collect_empty() -> None:
    from tartarus_v2.features import collect_argparse_commands
    import argparse

    p = argparse.ArgumentParser()
    assert collect_argparse_commands(p) == set()
