"""GitHub release check and menu wiring."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from tartarus_v2.gui.controllers import AppController
from tartarus_v2.updater import UpdateCheck, check_for_update, install_update, os_euid_is_root, parse_version


class _Body:
    def __init__(self, data: bytes = b"deb") -> None:
        self._data = data

    def read(self, _n: int = -1) -> bytes:
        data, self._data = self._data, b""
        return data

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *_a: object) -> bool:
        return False


def test_parse_version() -> None:
    assert parse_version("v0.7.10") == (0, 7, 10)
    assert parse_version("0.7.2") < parse_version("0.7.3")
    with pytest.raises(ValueError):
        parse_version("none")


def test_menu_includes_update_action() -> None:
    root = Path(__file__).resolve().parents[1]
    window = (root / "src/tartarus_v2/gui/window.py").read_text(encoding="utf-8")
    app = (root / "src/tartarus_v2/gui/app.py").read_text(encoding="utf-8")
    tray = (root / "src/tartarus_v2/gui/tray.py").read_text(encoding="utf-8")
    rules = (root / "scripts/99-tartarus-v2.rules").read_text(encoding="utf-8")
    assert 'menu.append("Check for updates' in window
    assert '"app.check_update"' in window
    assert 'SimpleAction.new("check_update"' in app
    assert "present_update_check" in app
    assert 'add_item("Check for updates' in tray
    assert 'KERNEL=="uinput"' in rules


def _response(payload: object) -> _Body:
    return _Body(json.dumps(payload).encode("utf-8"))


def test_check_finds_newer_deb() -> None:
    payload = {
        "tag_name": "v0.8.0",
        "html_url": "https://github.com/probityrules/razer-ubuntu/releases/tag/v0.8.0",
        "assets": [
            {
                "name": "tartarus-v2_0.8.0_all.deb",
                "browser_download_url": (
                    "https://github.com/probityrules/razer-ubuntu/releases/download/"
                    "v0.8.0/tartarus-v2_0.8.0_all.deb"
                ),
            }
        ],
    }
    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_response(payload)):
        info = check_for_update(current="0.7.3")
    assert info.update_available
    assert info.latest == "0.8.0"
    assert info.asset_name == "tartarus-v2_0.8.0_all.deb"


def test_check_up_to_date_and_errors() -> None:
    payload = {"tag_name": "v0.7.3", "html_url": "https://example.test", "assets": []}
    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_response(payload)):
        info = check_for_update(current="0.7.3")
    assert not info.update_available
    assert "up to date" in info.detail

    with patch(
        "tartarus_v2.updater.urllib.request.urlopen",
        side_effect=URLError("offline"),
    ):
        failed = check_for_update(current="0.7.3")
    assert failed.latest is None
    assert "Could not check" in failed.detail

    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_response({"tag_name": ""})):
        bad = check_for_update(current="0.7.3")
    assert "compare" in bad.detail or "Could not" in bad.detail


def test_check_fallback_deb_name() -> None:
    payload = {
        "tag_name": "v9.0.0",
        "html_url": "https://example.test/rel",
        "assets": [
            "skip-me",
            {
                "name": "custom_all.deb",
                "browser_download_url": (
                    "https://github.com/probityrules/razer-ubuntu/releases/download/"
                    "v9.0.0/custom_all.deb"
                ),
            },
        ],
    }
    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_response(payload)):
        info = check_for_update(current="0.1.0")
    assert info.asset_name == "custom_all.deb"
    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_response([])):
        bad = check_for_update(current="0.1.0")
    assert bad.latest is None


def test_check_without_deb_asset() -> None:
    payload = {"tag_name": "v9.0.0", "html_url": "https://example.test/rel", "assets": []}
    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_response(payload)):
        info = check_for_update(current="0.1.0")
    assert info.update_available
    assert info.asset_url is None
    assert ".deb" in info.detail


def test_install_refuses_and_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    current = UpdateCheck(
        current="0.7.3",
        latest="0.7.3",
        update_available=False,
        asset_url=None,
        asset_name=None,
        html_url=None,
        detail="up to date",
    )
    assert install_update(current) == "up to date"

    unsafe = UpdateCheck(
        current="0.7.3",
        latest="0.8.0",
        update_available=True,
        asset_url="https://evil.example/tartarus.deb",
        asset_name="tartarus-v2_0.8.0_all.deb",
        html_url=None,
        detail="update",
    )
    assert "Refusing" in install_update(unsafe)

    missing = UpdateCheck(
        current="0.7.3",
        latest="0.8.0",
        update_available=True,
        asset_url=None,
        asset_name=None,
        html_url=None,
        detail="no asset",
    )
    assert install_update(missing) == "no asset"

    url = (
        "https://github.com/probityrules/razer-ubuntu/releases/download/"
        "v0.8.0/tartarus-v2_0.8.0_all.deb"
    )
    good = UpdateCheck(
        current="0.7.3",
        latest="0.8.0",
        update_available=True,
        asset_url=url,
        asset_name="tartarus-v2_0.8.0_all.deb",
        html_url=None,
        detail="update",
    )
    def which(name: str) -> str | None:
        return {"apt-get": "/usr/bin/apt-get", "pkexec": "/usr/bin/pkexec"}.get(name)

    proc = MagicMock(returncode=0, stdout="", stderr="")
    fake_status = MagicMock(running=True, pid=42, detail="running")
    fake_stopped = MagicMock(running=False, pid=42, detail="stopped")
    fake_started = MagicMock(running=True, pid=99, detail="started")
    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_Body()):
        with patch("tartarus_v2.updater.shutil.which", side_effect=which):
            with patch("tartarus_v2.updater.os_euid_is_root", return_value=False):
                with patch("tartarus_v2.updater.subprocess.run", return_value=proc) as run:
                    with patch("tartarus_v2.daemon_control.status", return_value=fake_status):
                        with patch("tartarus_v2.daemon_control.stop", return_value=fake_stopped) as stop:
                            with patch(
                                "tartarus_v2.daemon_control.restart",
                                return_value=fake_started,
                            ) as restart:
                                msg = install_update(good)
    assert msg.startswith("Installed")
    assert "daemon restarted" in msg.lower()
    stop.assert_called_once()
    restart.assert_called_once()
    assert run.call_args.args[0][0].endswith("pkexec")
    deb = tmp_path / "tartarus-v2" / "tartarus-v2_0.8.0_all.deb"
    assert deb.is_file()


def test_install_failure_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    url = (
        "https://github.com/probityrules/razer-ubuntu/releases/download/"
        "v0.8.0/tartarus-v2_0.8.0_all.deb"
    )
    good = UpdateCheck(
        current="0.7.3",
        latest="0.8.0",
        update_available=True,
        asset_url=url,
        asset_name=None,
        html_url=None,
        detail="update",
    )
    with patch("tartarus_v2.updater.urllib.request.urlopen", side_effect=URLError("nope")):
        with patch("tartarus_v2.daemon_control.status", return_value=MagicMock(running=False)):
            assert "could not download" in install_update(good)

    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_Body()):
        with patch("tartarus_v2.updater.shutil.which", return_value=None):
            with patch("tartarus_v2.daemon_control.status", return_value=MagicMock(running=False)):
                assert "apt-get was not found" in install_update(good)

    def which_sudo(name: str) -> str | None:
        return {"apt-get": "/usr/bin/apt-get", "sudo": "/usr/bin/sudo"}.get(name)

    failed = MagicMock(returncode=1, stdout="", stderr="boom")
    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_Body()):
        with patch("tartarus_v2.updater.shutil.which", side_effect=which_sudo):
            with patch("tartarus_v2.updater.os_euid_is_root", return_value=False):
                with patch("tartarus_v2.updater.subprocess.run", return_value=failed):
                    with patch(
                        "tartarus_v2.daemon_control.status",
                        return_value=MagicMock(running=False),
                    ):
                        assert "Update failed" in install_update(good)

    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_Body()):
        with patch(
            "tartarus_v2.updater.shutil.which",
            side_effect=lambda n: "/usr/bin/apt-get" if n == "apt-get" else None,
        ):
            with patch("tartarus_v2.updater.os_euid_is_root", return_value=False):
                with patch(
                    "tartarus_v2.daemon_control.status",
                    return_value=MagicMock(running=False),
                ):
                    assert "pkexec/sudo not found" in install_update(good)

    with patch("tartarus_v2.updater.urllib.request.urlopen", return_value=_Body()):
        with patch(
            "tartarus_v2.updater.shutil.which",
            side_effect=lambda n: "/usr/bin/apt-get" if n == "apt-get" else None,
        ):
            with patch("tartarus_v2.updater.os_euid_is_root", return_value=True):
                with patch("tartarus_v2.updater.subprocess.run", side_effect=OSError("nope")):
                    with patch(
                        "tartarus_v2.daemon_control.status",
                        return_value=MagicMock(running=False),
                    ):
                        assert "Update failed" in install_update(good)
    assert os_euid_is_root() is False


def test_gui_relaunch_command() -> None:
    from tartarus_v2.gui.update_dialog import _gui_relaunch_command

    with patch("tartarus_v2.gui.update_dialog.shutil.which", return_value="/usr/bin/tartarus-v2"):
        assert _gui_relaunch_command(debug=True) == [
            "/usr/bin/tartarus-v2",
            "gui",
            "--debug",
        ]
    with patch("tartarus_v2.gui.update_dialog.shutil.which", return_value=None):
        cmd = _gui_relaunch_command(debug=False)
        assert cmd[-1] == "gui"
        assert "tartarus_v2" in cmd


def test_actions_and_controller_wrappers() -> None:
    info = UpdateCheck(
        current="0.7.3",
        latest="0.7.3",
        update_available=False,
        asset_url=None,
        asset_name=None,
        html_url=None,
        detail="up to date",
    )
    with patch("tartarus_v2.updater.check_for_update", return_value=info):
        from tartarus_v2 import actions

        assert actions.check_for_update().detail == "up to date"
        assert AppController().check_for_update().detail == "up to date"
    with patch("tartarus_v2.updater.install_update", return_value="Installed tartarus-v2 0.8.0."):
        from tartarus_v2 import actions

        assert actions.install_update(info).startswith("Installed")


def test_cli_update(capsys: pytest.CaptureFixture[str]) -> None:
    from tartarus_v2.cli import main

    info = UpdateCheck(
        current="0.7.3",
        latest="0.8.0",
        update_available=True,
        asset_url="https://github.com/probityrules/razer-ubuntu/releases/download/v0.8.0/x.deb",
        asset_name="x.deb",
        html_url=None,
        detail="Update available: 0.7.3 → 0.8.0.",
    )
    with patch("tartarus_v2.cli.actions.check_for_update", return_value=info):
        assert main(["update"]) == 0
    out = capsys.readouterr().out
    assert "update --install" in out

    with patch("tartarus_v2.cli.actions.check_for_update", return_value=info):
        with patch("tartarus_v2.cli.actions.install_update", return_value="Installed tartarus-v2 0.8.0."):
            assert main(["update", "--install"]) == 0

    offline = UpdateCheck(
        current="0.7.3",
        latest=None,
        update_available=False,
        asset_url=None,
        asset_name=None,
        html_url=None,
        detail="Could not check for updates: offline",
    )
    with patch("tartarus_v2.cli.actions.check_for_update", return_value=offline):
        assert main(["update"]) == 1
