"""Submit issue reports to a Notefully relay (no screenshots)."""

from __future__ import annotations

import json
import logging
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
# Notefully widget max; delivery plugins only render context.console.
MAX_CONSOLE_LINES = 80
# Extra log lines appended to the human-readable message (always visible in inbox).
MAX_MESSAGE_LOG_CHARS = 24_000
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
    """Build a fresh diagnose dump at call time (never reuse a prior GUI dump)."""
    from datetime import datetime, timezone

    from tartarus_v2.diagnose import build_report

    generated = datetime.now(timezone.utc).isoformat()
    try:
        # Always regenerate: live system snapshot for this submit only.
        text = build_report(listen_seconds=0.0, skip_probe=not include_probe)
    except Exception as exc:  # noqa: BLE001
        text = f"(diagnose failed: {exc})"
    header = (
        f"tartarus-v2 notefully diagnose\n"
        f"generated_utc={generated}\n"
        f"(fresh snapshot at submit; not a cached Diagnose-page dump)\n"
    )
    text = header + "\n" + text
    if len(text) > MAX_DIAGNOSTICS_CHARS:
        text = text[:MAX_DIAGNOSTICS_CHARS] + "\n\n…(truncated)…"
    return text


def _flush_logging() -> None:
    """Ensure file handlers write buffered lines before we read the log."""
    root = logging.getLogger("tartarus_v2")
    for handler in list(root.handlers):
        try:
            handler.flush()
        except Exception:  # noqa: BLE001
            pass


def gather_log_tail(limit: int = 200) -> str:
    """Read recent daemon/GUI log lines from disk (after flushing handlers)."""
    _flush_logging()
    path = log_path()
    try:
        if not path.exists():
            return f"(no log file yet at {path})"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            return f"(log file empty: {path})"
        return "\n".join(lines[-limit:])
    except OSError as exc:
        return f"(could not read {path}: {exc})"


def _guess_log_level(line: str) -> str:
    for part in line.split()[:8]:
        token = part.upper().rstrip(":")
        if token == "CRITICAL":
            return "error"
        if token == "ERROR":
            return "error"
        if token in ("WARNING", "WARN"):
            return "warn"
        if token == "INFO":
            return "info"
        if token == "DEBUG":
            return "log"
    return "log"


def log_tail_as_console(limit: int = MAX_CONSOLE_LINES) -> list[dict[str, Any]]:
    """Convert app log lines into Notefully ``context.console`` entries."""
    import time

    raw = gather_log_tail(limit=max(limit, 1))
    now = int(time.time() * 1000)
    entries: list[dict[str, Any]] = []
    for i, line in enumerate(raw.splitlines()):
        text = line.strip()
        if not text:
            continue
        entries.append(
            {
                "level": _guess_log_level(text),
                "text": text[:2000],
                "at": now - (len(raw.splitlines()) - i) * 10,
            }
        )
    if not entries:
        entries.append(
            {
                "level": "warn",
                "text": f"No tartarus-v2 log lines found at {log_path()}",
                "at": now,
            }
        )
    return entries[-limit:]


def build_context(
    *,
    author: str,
    diagnostics: str | None,
    console: list[dict[str, Any]] | None = None,
    log_tail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tail = log_tail if log_tail is not None else gather_log_tail()
    console_lines = console if console is not None else log_tail_as_console()
    ctx: dict[str, Any] = {
        "url": "app://tartarus-v2",
        "title": "Tartarus V2",
        "userAgent": f"tartarus-v2/{__version__} ({platform.system()}; {platform.machine()})",
        "os": platform.platform(),
        "browser": "tartarus-v2-native",
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
        # Notefully delivery / Tracker console panel (widget-compatible shape).
        "console": console_lines,
        "logTail": tail,
    }
    if diagnostics is not None:
        ctx["diagnostics"] = diagnostics
    if extra:
        ctx.update(extra)
    return ctx


def _compose_message(note: str, *, diagnostics: str) -> str:
    """User note plus a fresh diagnose dump (includes current log tail in §9)."""
    diag = diagnostics
    if len(diag) > MAX_MESSAGE_LOG_CHARS:
        diag = (
            diag[:MAX_MESSAGE_LOG_CHARS]
            + "\n…(truncated in message; full copy in context.diagnostics)…"
        )
    parts = [
        note.strip(),
        "",
        "---",
        "## diagnose dump (generated at submit)",
        "```",
        diag,
        "```",
    ]
    text = "\n".join(parts)
    max_total = MAX_DIAGNOSTICS_CHARS + 8_000
    if len(text) > max_total:
        text = text[:max_total] + "\n…(truncated)…"
    return text


def _checkpoint_log(note: str) -> None:
    """Write a marker so the log has a clear report boundary before we snapshot it."""
    log = logging.getLogger("tartarus_v2.notefully")
    snippet = note.replace("\n", " ").strip()[:120]
    log.info("Preparing Notefully report: %s", snippet or "(empty note)")
    _flush_logging()


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
    include_diagnostics: bool = True,  # noqa: ARG001 — always gathered fresh; kept for callers
    config: NotefullyConfig | None = None,
    timeout: float = 45.0,
) -> SubmitResult:
    """POST a text report with a fresh diagnose dump (+ console log) to Notefully."""
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

    # Fresh snapshot only: checkpoint → flush → rebuild diagnose + log (no cache).
    _checkpoint_log(note)
    _flush_logging()
    diagnostics = gather_diagnostics()
    log_tail = gather_log_tail()
    console = log_tail_as_console()
    message_body = _compose_message(note, diagnostics=diagnostics)

    fields = {
        "message": message_body,
        "kind": kind_id,
        "version": __version__,
        "author": reporter,
        "name": REPORT_NAME,
        "context": json.dumps(
            build_context(
                author=reporter,
                diagnostics=diagnostics,
                console=console,
                log_tail=log_tail,
            ),
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
