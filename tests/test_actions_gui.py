"""Action + controller tests with mocks / temp profiles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tartarus_v2 import actions
from tartarus_v2.gui.controllers import (
    BindingsController,
    DaemonController,
    DeviceController,
    DiagnoseController,
    LightingController,
    ProfilesController,
)
from tartarus_v2.diagnose import COPY_FROM, COPY_TO, build_report


@pytest.fixture()
def profile_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    return cache


def test_lighting_effects_list() -> None:
    assert "static" in actions.LIGHTING_EFFECTS
    assert LightingController().list_effects() == actions.LIGHTING_EFFECTS


@patch("tartarus_v2.actions.set_effect")
def test_lighting_apply(mock_set: MagicMock) -> None:
    LightingController().apply_effect("static", rgb="FF0000")
    mock_set.assert_called_once()


@patch("tartarus_v2.actions.device_info", return_value={"firmware": "v1", "serial": "S", "brightness": 1})
def test_device_refresh(mock_info: MagicMock) -> None:
    assert DeviceController().refresh_device()["firmware"] == "v1"


def test_profiles_roundtrip(profile_home: Path) -> None:
    ctrl = ProfilesController()
    items = ctrl.refresh_profiles()
    assert any(i["name"] == "default" for i in items)
    data = ctrl.show_profile("default")
    assert "hypershift" in data
    assert "standard" in data
    path = ctrl.open_profiles_dir()
    assert path.exists()
    ctrl.activate_profile("default")
    dup = ctrl.duplicate_profile("default", "arena")
    assert dup.exists()
    names = [i["name"] for i in ctrl.refresh_profiles()]
    assert "arena" in names
    created = ctrl.create_profile("fresh")
    assert created.exists()
    assert "fresh" in [i["name"] for i in ctrl.refresh_profiles()]


def test_bindings_hypershift(profile_home: Path) -> None:
    ctrl = BindingsController()
    data = ctrl.load_bindings("default")
    assert data["hypershift_key"]
    with patch("tartarus_v2.actions.nudge_daemon_reload", return_value="reload signaled") as nudge:
        updated = ctrl.set_hypershift_key("default", "thumb")
        assert updated["hypershift_key"] == "thumb"
        saved = ctrl.save_bindings(
            "default",
            "hypershift",
            {"key_01": "F1", "key_02": {"type": "macro", "steps": [{"tap": "a"}]}},
            hypershift_key="thumb",
        )
        assert saved["hypershift"]["bindings"]["key_01"] == "F1"
        assert nudge.call_count >= 2


@patch("tartarus_v2.gui.controllers.daemon_control.start")
@patch("tartarus_v2.gui.controllers.daemon_control.stop")
@patch("tartarus_v2.gui.controllers.daemon_control.status")
def test_daemon_controller(mock_status: MagicMock, mock_stop: MagicMock, mock_start: MagicMock) -> None:
    from tartarus_v2.daemon_control import DaemonStatus

    mock_start.return_value = DaemonStatus(running=True, pid=1, detail="started")
    mock_stop.return_value = DaemonStatus(running=False, detail="stopped")
    mock_status.return_value = DaemonStatus(running=False, detail="no pid file")
    ctrl = DaemonController()
    assert ctrl.start_daemon().running
    assert not ctrl.stop_daemon().running
    assert not ctrl.daemon_status().running


def test_autostart_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    from tartarus_v2 import autostart

    assert not autostart.is_autostart_enabled()
    path = autostart.set_autostart_enabled(True)
    assert path.exists()
    assert autostart.is_autostart_enabled()
    autostart.set_autostart_enabled(False)
    assert not autostart.is_autostart_enabled()
    assert DaemonController().is_autostart_enabled() is False


def test_diagnose_report_banners() -> None:
    report = build_report(skip_probe=True)
    assert COPY_FROM in report
    assert COPY_TO in report
    assert "## 1. Header" in report
    assert "## 7. Live probe" in report
    assert "## 10. Issues / remediation" in report


def test_diagnose_controller(tmp_path: Path) -> None:
    ctrl = DiagnoseController()
    fake = f"{COPY_FROM}\nhello\n{COPY_TO}\n"
    with patch("tartarus_v2.diagnose.build_report", return_value=fake):
        text = ctrl.run_diagnose(skip_probe=True)
    assert "hello" in text
    assert ctrl.copy_report() == text
    out = ctrl.save_report(tmp_path / "out.log")
    assert out.read_text(encoding="utf-8") == text


def test_actions_run_diagnose(tmp_path: Path) -> None:
    out = tmp_path / "d.log"
    with patch(
        "tartarus_v2.diagnose.build_report",
        return_value=f"{COPY_FROM}\nbody\n{COPY_TO}\n",
    ):
        report = actions.run_diagnose(out=str(out), skip_probe=True, print_report=False)
    assert "body" in report
    assert out.exists()
