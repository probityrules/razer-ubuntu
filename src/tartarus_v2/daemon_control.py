"""Start/stop/status for the remap+lighting daemon subprocess."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from tartarus_v2.logging_util import cache_dir

PID_FILE_NAME = "daemon.pid"


def pid_path() -> Path:
    return cache_dir() / PID_FILE_NAME


@dataclass
class DaemonStatus:
    running: bool
    pid: int | None = None
    detail: str = ""


def _read_pid() -> int | None:
    path = pid_path()
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def status() -> DaemonStatus:
    pid = _read_pid()
    if pid is None:
        return DaemonStatus(running=False, detail="no pid file")
    if _pid_alive(pid):
        return DaemonStatus(running=True, pid=pid, detail="running")
    try:
        pid_path().unlink(missing_ok=True)
    except OSError:
        pass
    return DaemonStatus(running=False, pid=pid, detail="stale pid file removed")


def _recent_daemon_error() -> str:
    """Last ERROR line from the daemon log, for an immediate-exit message."""
    try:
        from tartarus_v2.logging_util import log_path

        path = log_path()
        if not path.is_file():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines[-40:]):
        if " ERROR " not in line:
            continue
        msg = line.split(" ERROR ", 1)[-1].strip()
        if msg:
            return msg[:500]
    return ""


def start(profile: str | None = None, debug: bool = False) -> DaemonStatus:
    current = status()
    if current.running:
        return DaemonStatus(running=True, pid=current.pid, detail="already running")

    cmd = [sys.executable, "-m", "tartarus_v2", "daemon"]
    if profile:
        cmd.extend(["--profile", profile])
    if debug:
        cmd.append("--debug")

    # Detach so GUI/CLI can return
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "start_new_session": True,
    }
    proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
    pid_path().write_text(str(proc.pid) + "\n", encoding="utf-8")
    time.sleep(0.2)
    if proc.poll() is not None:
        try:
            pid_path().unlink(missing_ok=True)
        except OSError:
            pass
        detail = f"daemon exited immediately code={proc.returncode}"
        reason = _recent_daemon_error()
        if reason:
            detail = f"{detail}: {reason}"
        return DaemonStatus(
            running=False,
            pid=proc.pid,
            detail=detail,
        )
    return DaemonStatus(running=True, pid=proc.pid, detail="started")


def stop(timeout: float = 5.0) -> DaemonStatus:
    current = status()
    if not current.running or current.pid is None:
        return DaemonStatus(running=False, detail="not running")

    pid = current.pid
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_path().unlink(missing_ok=True)
        return DaemonStatus(running=False, detail="already gone")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            pid_path().unlink(missing_ok=True)
            return DaemonStatus(running=False, pid=pid, detail="stopped")
        time.sleep(0.1)

    try:
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except ProcessLookupError:
        pass
    pid_path().unlink(missing_ok=True)
    return DaemonStatus(running=False, pid=pid, detail="killed")


def reload() -> DaemonStatus:
    """Ask a running daemon to re-read the active profile (SIGHUP)."""
    current = status()
    if not current.running or current.pid is None:
        return DaemonStatus(running=False, detail="daemon not running")

    sighup = getattr(signal, "SIGHUP", None)
    if sighup is None:
        return DaemonStatus(
            running=True,
            pid=current.pid,
            detail="reload not supported on this OS",
        )

    try:
        os.kill(current.pid, sighup)
    except ProcessLookupError:
        try:
            pid_path().unlink(missing_ok=True)
        except OSError:
            pass
        return DaemonStatus(running=False, detail="daemon gone")
    except OSError as exc:
        return DaemonStatus(
            running=True,
            pid=current.pid,
            detail=f"reload failed: {exc}",
        )
    return DaemonStatus(running=True, pid=current.pid, detail="reload signaled")
