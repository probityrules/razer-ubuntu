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
