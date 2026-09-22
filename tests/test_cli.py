"""CLI parser and dispatch tests (mocked actions)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tartarus_v2.cli import build_parser, main


def test_parser_all_top_level_commands() -> None:
    parser = build_parser()
    for cmd in (
        ["diagnose"],
        ["diagnose", "--skip-probe", "--listen", "3", "--out", "/tmp/x.log"],
        ["daemon", "--debug", "--profile", "default"],
        ["daemon", "--background"],
        ["uninstall"],
        ["fix-permissions"],
        ["set-effect", "static", "--rgb", "FF0000"],
        ["set-brightness", "200"],
        ["profile", "list"],
        ["profile", "show", "default"],
        ["profile", "use", "default"],
        ["profile", "path"],
        ["info"],
        ["gui"],
    ):
        args = parser.parse_args(cmd)
        assert args.command == cmd[0]


def test_unknown_effect_rejected() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["set-effect", "not-an-effect"])


@patch("tartarus_v2.cli.actions.run_diagnose")
def test_main_diagnose(mock_diag: MagicMock) -> None:
    assert main(["diagnose", "--skip-probe", "--out", "x.log"]) == 0
    mock_diag.assert_called_once()
    kwargs = mock_diag.call_args.kwargs
    assert kwargs["skip_probe"] is True
    assert kwargs["out"] == "x.log"


@patch("tartarus_v2.cli.actions.run_daemon_foreground")
def test_main_daemon(mock_daemon: MagicMock) -> None:
    assert main(["daemon", "--profile", "default", "--debug"]) == 0
    mock_daemon.assert_called_once_with(profile="default", debug=True)


@patch("tartarus_v2.cli.actions.start_daemon_background")
def test_main_daemon_background(mock_bg: MagicMock) -> None:
    from tartarus_v2.daemon_control import DaemonStatus

    mock_bg.return_value = DaemonStatus(running=True, pid=9, detail="started")
    assert main(["daemon", "--background"]) == 0
    mock_bg.assert_called_once()


@patch("tartarus_v2.cli.actions.uninstall_package", return_value="tartarus-v2 removed")
def test_main_uninstall(mock_un: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["uninstall"]) == 0
    assert "removed" in capsys.readouterr().out
    mock_un.assert_called_once()


@patch("tartarus_v2.cli.actions.fix_permissions", return_value="Added user to input,plugdev")
def test_main_fix_permissions(mock_fix: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix-permissions"]) == 0
    assert "input" in capsys.readouterr().out
    mock_fix.assert_called_once()


@patch("tartarus_v2.cli.actions.set_effect")
def test_main_set_effect(mock_effect: MagicMock) -> None:
    assert main(["set-effect", "spectrum"]) == 0
    assert mock_effect.call_args.args[0] == "spectrum"


@patch("tartarus_v2.cli.actions.set_brightness")
def test_main_set_brightness(mock_b: MagicMock) -> None:
    assert main(["set-brightness", "128"]) == 0
    mock_b.assert_called_once_with(128, debug=False)


@patch("tartarus_v2.cli.actions.list_profiles", return_value=[{"name": "default", "active": True}])
def test_main_profile_list(mock_list: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profile", "list"]) == 0
    assert "default" in capsys.readouterr().out


@patch("tartarus_v2.cli.actions.show_profile", return_value={"name": "default"})
@patch("tartarus_v2.cli.actions.format_profile_json", return_value='{"name": "default"}')
def test_main_profile_show(_fmt: MagicMock, _show: MagicMock) -> None:
    assert main(["profile", "show"]) == 0


@patch("tartarus_v2.cli.actions.use_profile", return_value="default")
def test_main_profile_use(mock_use: MagicMock) -> None:
    assert main(["profile", "use", "default"]) == 0
    mock_use.assert_called_once_with("default")


@patch("tartarus_v2.cli.actions.profiles_path")
def test_main_profile_path(mock_path: MagicMock, tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    mock_path.return_value = tmp_path
    assert main(["profile", "path"]) == 0
    assert str(tmp_path) in capsys.readouterr().out


@patch(
    "tartarus_v2.cli.actions.device_info",
    return_value={"firmware": "v1.0", "serial": "ABC", "brightness": 10},
)
def test_main_info(mock_info: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "v1.0" in out
    assert "ABC" in out


@patch("tartarus_v2.cli.actions.launch_gui", return_value=0)
def test_main_gui(mock_gui: MagicMock) -> None:
    assert main(["gui"]) == 0
    mock_gui.assert_called_once()
