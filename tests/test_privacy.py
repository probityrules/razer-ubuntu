"""Tests for report privacy redaction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tartarus_v2.diagnose import COPY_FROM, COPY_TO, build_report
from tartarus_v2.privacy import (
    PLACEHOLDER_HOME,
    PLACEHOLDER_HOST,
    PLACEHOLDER_SERIAL,
    PLACEHOLDER_USER,
    redact_report_text,
)


def test_redact_report_text_strips_identity(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home" / "nidsviper"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("USER", "nidsviper")
    monkeypatch.setenv("USERNAME", "nidsviper")
    monkeypatch.setenv("HOSTNAME", "ubdesky")
    monkeypatch.setattr("tartarus_v2.privacy.Path.home", lambda: home)
    monkeypatch.setattr("tartarus_v2.privacy.platform.node", lambda: "ubdesky.local")
    with patch("tartarus_v2.permissions.current_username", return_value="nidsviper"):
        sample = (
            "hostname=ubdesky\n"
            "uname=Linux ubdesky 7.0.0-34-generic\n"
            "user=nidsviper\n"
            "session_groups=['adm', 'nidsviper', 'input']\n"
            f"daemon log: {home.as_posix()}/.cache/tartarus-v2/tartarus-v2.log\n"
            f"autostart: user_desktop={home.as_posix()}/.config/autostart/x.desktop\n"
            "serial=b'ABC123XYZ'\n"
            "  iSerial               0  RZ09-SECRET\n"
            "Opened via /dev/hidraw5\n"
        )
        out = redact_report_text(sample)

    assert "nidsviper" not in out
    assert "ubdesky" not in out
    assert home.as_posix() not in out
    assert PLACEHOLDER_HOST in out
    assert f"user={PLACEHOLDER_USER}" in out
    assert PLACEHOLDER_HOME in out
    assert PLACEHOLDER_SERIAL in out
    assert "RZ09-SECRET" not in out
    assert "/dev/hidraw5" in out
    assert "input" in out


def test_build_report_redacts_header_and_home(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "alice"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setenv("USERNAME", "alice")
    monkeypatch.setenv("HOSTNAME", "devbox")
    monkeypatch.setattr("tartarus_v2.privacy.Path.home", lambda: home)
    monkeypatch.setattr("tartarus_v2.privacy.platform.node", lambda: "devbox")
    with patch("tartarus_v2.permissions.current_username", return_value="alice"):
        report = build_report(skip_probe=True)

    assert f"hostname={PLACEHOLDER_HOST}" in report
    assert f"user={PLACEHOLDER_USER}" in report
    assert "alice" not in report
    assert "devbox" not in report
    assert COPY_FROM in report
    assert COPY_TO in report
