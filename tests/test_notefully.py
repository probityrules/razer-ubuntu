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


@patch("tartarus_v2.notefully.gather_diagnostics", return_value="## DIAG\nok")
@patch("tartarus_v2.notefully.gather_log_tail", return_value="log line")
@patch("tartarus_v2.notefully.save_author")
@patch("tartarus_v2.notefully.urlopen")
def test_submit_success(
    mock_urlopen: MagicMock,
    mock_save_author: MagicMock,
    _log: MagicMock,
    _diag: MagicMock,
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
    body = req.data
    assert b"Keys 16-19 do nothing" in body
    assert b'name="kind"' in body
    assert b"bug" in body
    assert b"tartarus-v2" in body
    assert b"## DIAG" in body


def test_submit_does_not_persist_anonymous_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[str] = []
    monkeypatch.setattr(nf, "save_author", lambda a: saved.append(a))
    monkeypatch.setattr(nf, "gather_diagnostics", lambda: "")
    monkeypatch.setattr(nf, "gather_log_tail", lambda limit=120: "")

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

@patch("tartarus_v2.notefully.urlopen")
def test_submit_http_error(mock_urlopen: MagicMock) -> None:
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


@patch("tartarus_v2.notefully.urlopen")
def test_submit_network_error(mock_urlopen: MagicMock) -> None:
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
    assert nf.gather_diagnostics() == "DUMP"
    mock_build.assert_called_once_with(listen_seconds=0.0, skip_probe=True)


def test_build_context_includes_diagnostics() -> None:
    with patch.object(nf, "gather_log_tail", return_value="tail"):
        ctx = nf.build_context(author="Ada", diagnostics="dump text")
    assert ctx["author"] == "Ada"
    assert ctx["diagnostics"] == "dump text"
    assert ctx["app"]["name"] == "tartarus-v2"
    assert ctx["logTail"] == "tail"
