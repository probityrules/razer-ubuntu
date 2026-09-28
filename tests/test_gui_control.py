"""GUI process detect / restart helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from tartarus_v2 import gui_control


def test_looks_like_gui() -> None:
    assert gui_control._looks_like_gui("/usr/bin/tartarus-v2 gui")  # noqa: SLF001
    assert gui_control._looks_like_gui("python3 -m tartarus_v2 gui")  # noqa: SLF001
    assert not gui_control._looks_like_gui("/usr/bin/tartarus-v2 daemon")  # noqa: SLF001
    assert not gui_control._looks_like_gui("/usr/bin/tartarus-v2 gui --restart")  # noqa: SLF001
    assert not gui_control._looks_like_gui("firefox")  # noqa: SLF001


def test_restart_if_running_noop_when_closed() -> None:
    with patch.object(gui_control, "find_gui_pids", return_value=[]):
        st = gui_control.restart_if_running()
    assert not st.running
    assert "not running" in st.detail


def test_restart_if_running_relaunches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gui_control, "find_gui_pids", lambda **_k: [4242])
    monkeypatch.setattr(
        gui_control,
        "_environ_map",
        lambda _pid: {
            "DISPLAY": ":0",
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": str(tmp_path),
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/bus",
        },
    )
    monkeypatch.setattr(gui_control, "_stop_pids", lambda *_a, **_k: None)

    popped: list[object] = []

    class FakeProc:
        pid = 9999

    def fake_popen(cmd, **kwargs):  # noqa: ANN001
        popped.append((cmd, kwargs.get("env")))
        return FakeProc()

    monkeypatch.setattr(gui_control.subprocess, "Popen", fake_popen)
    st = gui_control.restart_if_running()
    assert st.running
    assert st.pids == [9999]
    assert "restarted" in st.detail
    assert popped
    cmd, env = popped[0]
    assert "gui" in cmd
    assert env["DISPLAY"] == ":0"
    assert env["WAYLAND_DISPLAY"] == "wayland-0"


def test_postinst_restarts_gui() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "packaging/postinst.sh"
    ).read_text(encoding="utf-8")
    assert "gui --restart" in text
