"""Tests for Notefully report submission."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from tartarus_v2 import notefully as nf


def test_load_config_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARTARUS_NOTEFULLY_ENDPOINT", raising=False)
    monkeypatch.delenv("TARTARUS_NOTEFULLY_KEY", raising=False)
    monkeypatch.setattr(nf, "config_path", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(nf, "EMBEDDED_PROJECT_KEY", "")
    cfg = nf.load_config()
    assert cfg.endpoint == nf.DEFAULT_ENDPOINT
    assert cfg.project_key == ""
    assert not cfg.configured


def test_load_config_env_and_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "notefully.json"
    cfg_file.write_text(
        json.dumps({"endpoint": "https://example.test/notefully", "projectKey": "nfk_file"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(nf, "config_path", lambda: cfg_file)
    monkeypatch.delenv("TARTARUS_NOTEFULLY_ENDPOINT", raising=False)
    monkeypatch.delenv("TARTARUS_NOTEFULLY_KEY", raising=False)
    monkeypatch.setattr(nf, "EMBEDDED_PROJECT_KEY", "nfk_embedded")
    cfg = nf.load_config()
    assert cfg.endpoint == "https://example.test/notefully"
    assert cfg.project_key == "nfk_file"

    monkeypatch.setenv("TARTARUS_NOTEFULLY_KEY", "nfk_env")
    monkeypatch.setenv("TARTARUS_NOTEFULLY_ENDPOINT", "https://env.test/nf")
    cfg = nf.load_config()
    assert cfg.endpoint == "https://env.test/nf"
    assert cfg.project_key == "nfk_env"


def test_save_and_load_author(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nf, "author_path", lambda: tmp_path / "report-author.txt")
    assert nf.load_author() == ""
    nf.save_author("Ada")
    assert nf.load_author() == "Ada"
    nf.save_author("  ")
    assert nf.load_author() == ""


def test_submit_requires_config() -> None:
    result = nf.submit_report(
        message="hello",
        config=nf.NotefullyConfig(endpoint=nf.DEFAULT_ENDPOINT, project_key=""),
    )
    assert not result.ok
    assert "not configured" in result.error.lower()


def test_submit_requires_message() -> None:
    result = nf.submit_report(
        message="  ",
        config=nf.NotefullyConfig(endpoint="https://example.test", project_key="nfk_x"),
    )
    assert not result.ok
    assert "note" in result.error.lower()


@patch("tartarus_v2.notefully._checkpoint_log")
@patch("tartarus_v2.notefully.gather_diagnostics", return_value="## DIAG\nok")
@patch("tartarus_v2.notefully.gather_log_tail", return_value="2026-01-01 INFO tartarus_v2: log line")
@patch(
    "tartarus_v2.notefully.log_tail_as_console",
    return_value=[{"level": "info", "text": "2026-01-01 INFO tartarus_v2: log line", "at": 1}],
)
@patch("tartarus_v2.notefully.save_author")
@patch("tartarus_v2.notefully.urlopen")
def test_submit_success(
    mock_urlopen: MagicMock,
    mock_save_author: MagicMock,
    _console: MagicMock,
    _log: MagicMock,
    _diag: MagicMock,
    _checkpoint: MagicMock,
) -> None:
    payload = {"id": "nf_abc123", "version": "0.4.0", "deliveries": {}}
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    mock_urlopen.return_value = resp

    result = nf.submit_report(
        message="Keys 16-19 do nothing",
        kind="bug",
        author="Derek",
        include_diagnostics=True,
        config=nf.NotefullyConfig(
            endpoint="https://example.test/notefully",
            project_key="nfk_test",
        ),
    )
    assert result.ok
    assert result.report_id == "nf_abc123"
    mock_save_author.assert_called_once_with("Derek")

    req = mock_urlopen.call_args.args[0]
    assert req.full_url == "https://example.test/notefully/v1/reports"
    assert req.get_header("X-notefully-key") == "nfk_test"
    body = req.data.decode("utf-8", errors="replace")
    assert "Keys 16-19 do nothing" in body
    assert 'name="kind"' in body
    assert "bug" in body
    assert "tartarus-v2" in body
    assert "## DIAG" in body
    assert "## diagnose dump (generated at submit)" in body
    assert '"console"' in body
    assert "log line" in body


def test_submit_does_not_persist_anonymous_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[str] = []
    monkeypatch.setattr(nf, "save_author", lambda a: saved.append(a))
    monkeypatch.setattr(nf, "gather_diagnostics", lambda: "")
    monkeypatch.setattr(nf, "gather_log_tail", lambda limit=200: "empty-ish")
    monkeypatch.setattr(nf, "log_tail_as_console", lambda limit=80: [])
    monkeypatch.setattr(nf, "_checkpoint_log", lambda note: None)

    payload = {"id": "nf_x"}
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False

    with patch.object(nf, "urlopen", return_value=resp):
        result = nf.submit_report(
            message="anonymous ok",
            author="",
            include_diagnostics=False,
            config=nf.NotefullyConfig(endpoint="https://example.test", project_key="nfk_x"),
        )
    assert result.ok
    assert saved == []


@patch("tartarus_v2.notefully._checkpoint_log")
@patch("tartarus_v2.notefully.gather_log_tail", return_value="tail")
@patch("tartarus_v2.notefully.log_tail_as_console", return_value=[])
@patch("tartarus_v2.notefully.urlopen")
def test_submit_http_error(
    mock_urlopen: MagicMock,
    _console: MagicMock,
    _log: MagicMock,
    _checkpoint: MagicMock,
) -> None:
    err = HTTPError(
        "https://example.test/v1/reports",
        401,
        "Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=BytesIO(b'{"error":"Invalid project key"}'),
    )
    mock_urlopen.side_effect = err
    result = nf.submit_report(
        message="hi",
        include_diagnostics=False,
        config=nf.NotefullyConfig(endpoint="https://example.test", project_key="nfk_bad"),
    )
    assert not result.ok
    assert "Invalid project key" in result.error


@patch("tartarus_v2.notefully._checkpoint_log")
@patch("tartarus_v2.notefully.gather_log_tail", return_value="tail")
@patch("tartarus_v2.notefully.log_tail_as_console", return_value=[])
@patch("tartarus_v2.notefully.urlopen")
def test_submit_network_error(
    mock_urlopen: MagicMock,
    _console: MagicMock,
    _log: MagicMock,
    _checkpoint: MagicMock,
) -> None:
    mock_urlopen.side_effect = URLError("connection refused")
    result = nf.submit_report(
        message="hi",
        include_diagnostics=False,
        config=nf.NotefullyConfig(endpoint="https://example.test", project_key="nfk_x"),
    )
    assert not result.ok
    assert "Network error" in result.error


@patch("tartarus_v2.diagnose.build_report", return_value="DUMP")
def test_gather_diagnostics(mock_build: MagicMock) -> None:
    text = nf.gather_diagnostics()
    assert "DUMP" in text
    assert "generated_utc=" in text
    mock_build.assert_called_once_with(listen_seconds=0.0, skip_probe=True)


def test_build_context_includes_console_and_diagnostics() -> None:
    with (
        patch.object(nf, "gather_log_tail", return_value="INFO hello"),
        patch.object(
            nf,
            "log_tail_as_console",
            return_value=[{"level": "info", "text": "INFO hello", "at": 1}],
        ),
    ):
        ctx = nf.build_context(author="Ada", diagnostics="dump text")
    assert ctx["author"] == "Ada"
    assert ctx["diagnostics"] == "dump text"
    assert ctx["app"]["name"] == "tartarus-v2"
    assert ctx["logTail"] == "INFO hello"
    assert ctx["console"][0]["text"] == "INFO hello"


def test_log_tail_as_console_parses_levels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_file = tmp_path / "tartarus-v2.log"
    log_file.write_text(
        "2026-01-01T00:00:00.000 INFO tartarus_v2: started\n"
        "2026-01-01T00:00:01.000 ERROR tartarus_v2.remap: Failed to grab\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(nf, "log_path", lambda: log_file)
    monkeypatch.setattr(nf, "_flush_logging", lambda: None)
    entries = nf.log_tail_as_console(limit=80)
    assert entries[-1]["level"] == "error"
    assert "Failed to grab" in entries[-1]["text"]
    assert entries[0]["level"] == "info"


def test_compose_message_includes_diagnose() -> None:
    text = nf._compose_message(
        "pad dead",
        diagnostics="generated_utc=now\n## DIAG",
    )
    assert text.startswith("pad dead")
    assert "## diagnose dump (generated at submit)" in text
    assert "## DIAG" in text


def test_gather_diagnostics_is_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_build(**kwargs: object) -> str:
        calls.append(kwargs)
        return "=== COPY FROM HERE ===\nfresh-dump\n"

    monkeypatch.setattr("tartarus_v2.diagnose.build_report", fake_build)
    text = nf.gather_diagnostics()
    assert "generated_utc=" in text
    assert "fresh snapshot at submit" in text
    assert "fresh-dump" in text
    assert calls == [{"listen_seconds": 0.0, "skip_probe": True}]
