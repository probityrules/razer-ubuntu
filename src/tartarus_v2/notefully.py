"""Submit issue reports to a Notefully relay (no screenshots)."""

from __future__ import annotations

import json
import os
import platform
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tartarus_v2 import __version__
from tartarus_v2.constants import CACHE_DIR_NAME
from tartarus_v2.logging_util import cache_dir, log_path

# Hosted Makefully relay (no trailing slash required).
DEFAULT_ENDPOINT = "https://make.makefullystudios.com/notefully"
# Public project key from Showfully → Notefully → Settings (safe to embed).
# Override with TARTARUS_NOTEFULLY_KEY or ~/.config/tartarus-v2/notefully.json.
EMBEDDED_PROJECT_KEY = ""
REPORT_NAME = "tartarus-v2"
MAX_DIAGNOSTICS_CHARS = 180_000
KINDS = ("bug", "idea", "other")


@dataclass(frozen=True)
class NotefullyConfig:
    endpoint: str
    project_key: str

    @property
    def configured(self) -> bool:
        return bool(self.endpoint.strip() and self.project_key.strip())


@dataclass(frozen=True)
class SubmitResult:
    ok: bool
    report_id: str = ""
    error: str = ""
    raw: dict[str, Any] | None = None


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / CACHE_DIR_NAME / "notefully.json"


def author_path() -> Path:
    return cache_dir() / "report-author.txt"


def load_author() -> str:
    path = author_path()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_author(author: str) -> None:
    text = author.strip()
    path = author_path()
    try:
        if text:
            path.write_text(text + "\n", encoding="utf-8")
        elif path.exists():
            path.unlink()
    except OSError:
        pass


def _read_json_config() -> dict[str, Any]:
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_project_key(project_key: str) -> None:
    """Persist a public project key for future reports."""
    key = project_key.strip()
    data = _read_json_config()
    if key:
        data["projectKey"] = key
    else:
        data.pop("projectKey", None)
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def load_config() -> NotefullyConfig:
    file_cfg = _read_json_config()
    endpoint = (
        os.environ.get("TARTARUS_NOTEFULLY_ENDPOINT")
        or str(file_cfg.get("endpoint") or "")
        or DEFAULT_ENDPOINT
    ).rstrip("/")
    project_key = (
        os.environ.get("TARTARUS_NOTEFULLY_KEY")
        or str(file_cfg.get("projectKey") or file_cfg.get("project_key") or "")
        or EMBEDDED_PROJECT_KEY
    ).strip()
    return NotefullyConfig(endpoint=endpoint, project_key=project_key)


def gather_diagnostics(*, include_probe: bool = False) -> str:
    """Build a diagnose dump suitable for attaching to a Notefully report."""
    from tartarus_v2.diagnose import build_report

    try:
        text = build_report(listen_seconds=0.0, skip_probe=not include_probe)
    except Exception as exc:  # noqa: BLE001
        text = f"(diagnose failed: {exc})"
    if len(text) > MAX_DIAGNOSTICS_CHARS:
        text = text[:MAX_DIAGNOSTICS_CHARS] + "\n\n…(truncated)…"
    return text


def gather_log_tail(limit: int = 120) -> str:
    path = log_path()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-limit:])
    except OSError as exc:
        return f"(could not read {path}: {exc})"


def build_context(
    *,
    author: str,
    diagnostics: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "url": "app://tartarus-v2",
        "title": "Tartarus V2",
        "userAgent": f"tartarus-v2/{__version__} ({platform.system()}; {platform.machine()})",
        "os": platform.platform(),
        "language": os.environ.get("LANG") or os.environ.get("LC_ALL") or "",
        "timezone": _timezone_name(),
        "app": {
            "name": REPORT_NAME,
            "version": __version__,
            "logPath": str(log_path()),
        },
        "user": {
            "userId": None,
            "email": None,
            "displayName": author or None,
        },
        "author": author or "Anonymous",
        "logTail": gather_log_tail(),
    }
    if diagnostics is not None:
        ctx["diagnostics"] = diagnostics
    if extra:
        ctx.update(extra)
    return ctx


def _timezone_name() -> str:
    try:
        import time

        return time.tzname[time.daylight] if time.daylight else time.tzname[0]
    except Exception:  # noqa: BLE001
        return ""


def _encode_multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----TartarusNotefully{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"


def submit_report(
    *,
    message: str,
    kind: str = "bug",
    author: str = "",
    include_diagnostics: bool = True,
    config: NotefullyConfig | None = None,
    timeout: float = 45.0,
) -> SubmitResult:
    """POST a text report (+ optional diagnose dump in context) to Notefully."""
    cfg = config or load_config()
    if not cfg.configured:
        return SubmitResult(
            ok=False,
            error=(
                "Notefully is not configured. Set TARTARUS_NOTEFULLY_KEY "
                "or add projectKey to ~/.config/tartarus-v2/notefully.json."
            ),
        )

    note = message.strip()
    if not note:
        return SubmitResult(ok=False, error="Add a note before submitting.")

    kind_id = (kind or "bug").strip().lower() or "bug"
    typed_author = author.strip()
    if typed_author:
        save_author(typed_author)
    reporter = typed_author or "Anonymous"
    diagnostics = gather_diagnostics() if include_diagnostics else None
    fields = {
        "message": note,
        "kind": kind_id,
        "version": __version__,
        "author": reporter,
        "name": REPORT_NAME,
        "context": json.dumps(
            build_context(author=reporter, diagnostics=diagnostics),
            ensure_ascii=False,
        ),
        "annotations": "[]",
        "crop": json.dumps({"x": 0, "y": 0, "w": 1, "h": 1}),
    }
    body, content_type = _encode_multipart(fields)
    url = f"{cfg.endpoint}/v1/reports"
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": content_type,
            "X-Notefully-Key": cfg.project_key,
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — user/configured URL
            raw_text = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
        detail = _error_from_body(err_body) or exc.reason or str(exc)
        return SubmitResult(ok=False, error=f"{detail} (HTTP {exc.code})")
    except URLError as exc:
        return SubmitResult(ok=False, error=f"Network error: {exc.reason}")
    except TimeoutError:
        return SubmitResult(ok=False, error="Request timed out.")
    except Exception as exc:  # noqa: BLE001
        return SubmitResult(ok=False, error=str(exc))

    try:
        payload = json.loads(raw_text) if raw_text else {}
    except json.JSONDecodeError:
        payload = {}

    if status >= 400:
        return SubmitResult(
            ok=False,
            error=_error_from_body(raw_text) or f"Submit failed (HTTP {status})",
            raw=payload if isinstance(payload, dict) else None,
        )

    report_id = ""
    if isinstance(payload, dict):
        report_id = str(payload.get("id") or "")
    return SubmitResult(ok=True, report_id=report_id, raw=payload if isinstance(payload, dict) else None)


def _error_from_body(raw: str) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip()[:200]
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return raw.strip()[:200]
