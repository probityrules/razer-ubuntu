"""daemon_control unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tartarus_v2 import daemon_control


@pytest.fixture()
def pid_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path


def test_status_no_pid(pid_home: Path) -> None:
    st = daemon_control.status()
    assert not st.running


def test_start_stop(pid_home: Path) -> None:
    proc = MagicMock()
    proc.pid = 4242
    proc.poll.return_value = None

    with patch("tartarus_v2.daemon_control.subprocess.Popen", return_value=proc) as popen:
        st = daemon_control.start(profile="default", debug=True)
        assert st.running
        assert st.pid == 4242
        popen.assert_called_once()
        assert daemon_control.pid_path().read_text(encoding="utf-8").strip() == "4242"

    with patch("tartarus_v2.daemon_control._pid_alive", side_effect=[True, False]):
        with patch("tartarus_v2.daemon_control.os.kill") as kill:
            st = daemon_control.stop()
            assert not st.running
            kill.assert_called()


def test_reload_signals_running_daemon(pid_home: Path) -> None:
    daemon_control.pid_path().write_text("7777\n", encoding="utf-8")
    with patch("tartarus_v2.daemon_control._pid_alive", return_value=True):
        with patch("tartarus_v2.daemon_control.signal.SIGHUP", 1, create=True):
            with patch("tartarus_v2.daemon_control.os.kill") as kill:
                st = daemon_control.reload()
                assert st.running
                assert st.detail == "reload signaled"
                kill.assert_called_once()
                assert kill.call_args[0][0] == 7777


def test_reload_when_not_running(pid_home: Path) -> None:
    st = daemon_control.reload()
    assert not st.running
    assert "not running" in st.detail


def test_status_sees_systemd_when_no_pid(pid_home: Path) -> None:
    with patch("tartarus_v2.daemon_control.systemd_unit_active", return_value=True):
        st = daemon_control.status()
    assert st.running
    assert "systemd" in st.detail


def test_stop_stops_systemd_and_pid(pid_home: Path) -> None:
    daemon_control.pid_path().write_text("55\n", encoding="utf-8")
    with patch("tartarus_v2.daemon_control.systemd_unit_enabled", return_value=True):
        with patch("tartarus_v2.daemon_control.systemd_unit_active", side_effect=[True, False, False]):
            with patch(
                "tartarus_v2.daemon_control._systemctl_user",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ) as sysctl:
                with patch("tartarus_v2.daemon_control._pid_alive", side_effect=[True, False]):
                    with patch("tartarus_v2.daemon_control.os.kill") as kill:
                        st = daemon_control.stop()
    assert not st.running
    sysctl.assert_any_call("stop", daemon_control.USER_SERVICE)
    kill.assert_called()


def test_start_prefers_systemd_when_enabled(pid_home: Path) -> None:
    with patch("tartarus_v2.daemon_control.systemd_unit_enabled", return_value=True):
        with patch("tartarus_v2.daemon_control.systemd_unit_active", side_effect=[False, True]):
            with patch(
                "tartarus_v2.daemon_control._systemctl_user",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ) as sysctl:
                with patch("tartarus_v2.daemon_control.subprocess.Popen") as popen:
                    st = daemon_control.start()
    assert st.running
    assert "systemd" in st.detail
    sysctl.assert_called_with("start", daemon_control.USER_SERVICE)
    popen.assert_not_called()


def test_restart_uses_systemd_restart(pid_home: Path) -> None:
    with patch("tartarus_v2.daemon_control.stop", return_value=daemon_control.DaemonStatus(False)):
        with patch("tartarus_v2.daemon_control.systemd_unit_enabled", return_value=True):
            with patch("tartarus_v2.daemon_control.systemd_unit_active", return_value=True):
                with patch(
                    "tartarus_v2.daemon_control._systemctl_user",
                    return_value=MagicMock(returncode=0, stdout="", stderr=""),
                ) as sysctl:
                    with patch("tartarus_v2.daemon_control.time.sleep"):
                        st = daemon_control.restart()
    assert st.running
    assert "systemd" in st.detail
    sysctl.assert_called_with("restart", daemon_control.USER_SERVICE)


def test_start_reports_log_error_when_daemon_exits(pid_home: Path) -> None:
    log = pid_home / "tartarus-v2" / "tartarus-v2.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "2026-09-24T18:21:42.923 ERROR tartarus_v2.daemon: "
        "Remapper failed; keypad keys stay at firmware defaults: "
        "Cannot create the virtual keyboard (/dev/uinput): permission denied.\n",
        encoding="utf-8",
    )
    proc = MagicMock()
    proc.pid = 99
    proc.poll.return_value = 1
    proc.returncode = 1
    with patch("tartarus_v2.daemon_control.subprocess.Popen", return_value=proc):
        with patch("tartarus_v2.daemon_control.time.sleep"):
            st = daemon_control.start()
    assert not st.running
    assert "exited immediately" in st.detail
    assert "/dev/uinput" in st.detail
    assert not daemon_control.pid_path().exists()
