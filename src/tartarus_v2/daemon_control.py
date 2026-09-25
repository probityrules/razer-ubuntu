"""Start/stop/status for the remap+lighting daemon subprocess."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from tartarus_v2.logging_util import cache_dir

PID_FILE_NAME = "daemon.pid"
USER_SERVICE = "tartarus-v2.service"


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


def _systemctl_user(*args: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str] | None:
    """Run ``systemctl --user …``, or None when systemctl is unavailable."""
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return None
    try:
        return subprocess.run(  # noqa: S603
            [systemctl, "--user", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def systemd_unit_enabled() -> bool:
    """True when the user unit is enabled (preferred supervisor after install)."""
    proc = _systemctl_user("is-enabled", USER_SERVICE)
    return proc is not None and proc.returncode == 0


def systemd_unit_active() -> bool:
    """True when the user unit is currently active."""
    proc = _systemctl_user("is-active", USER_SERVICE)
    if proc is None or proc.returncode != 0:
        return False
    return (proc.stdout or "").strip() == "active"


def _clear_stale_pid() -> None:
    try:
        pid_path().unlink(missing_ok=True)
    except OSError:
        pass


def status() -> DaemonStatus:
    """Report whether a remapper is up (PID-file daemon and/or systemd unit)."""
    pid = _read_pid()
    if pid is not None:
        if _pid_alive(pid):
            return DaemonStatus(running=True, pid=pid, detail="running (background)")
        _clear_stale_pid()
    if systemd_unit_active():
        return DaemonStatus(running=True, pid=None, detail="running (systemd)")
    return DaemonStatus(running=False, detail="not running")


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


def _stop_pid_daemon(timeout: float = 5.0) -> str:
    """Stop the PID-file background daemon if present. Returns a short note."""
    pid = _read_pid()
    if pid is None:
        return "no pid file"
    if not _pid_alive(pid):
        _clear_stale_pid()
        return "stale pid cleared"
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_stale_pid()
        return "already gone"

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            _clear_stale_pid()
            return "background stopped"
        time.sleep(0.1)

    try:
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except ProcessLookupError:
        pass
    _clear_stale_pid()
    return "background killed"


def _stop_systemd() -> str:
    if not systemd_unit_enabled() and not systemd_unit_active():
        return "systemd idle"
    proc = _systemctl_user("stop", USER_SERVICE)
    if proc is None:
        return "systemctl unavailable"
    if proc.returncode == 0:
        # Wait briefly for the unit to drop.
        for _ in range(20):
            if not systemd_unit_active():
                return "systemd stopped"
            time.sleep(0.1)
        return "systemd stop signaled"
    err = (proc.stderr or proc.stdout or "").strip()
    return f"systemd stop failed ({err[:120] or proc.returncode})"


def stop(timeout: float = 5.0) -> DaemonStatus:
    """Stop every known remapper supervisor (systemd unit and PID-file daemon)."""
    notes = [_stop_systemd(), _stop_pid_daemon(timeout=timeout)]
    detail = "; ".join(notes)
    if status().running:
        return DaemonStatus(running=True, detail=f"still running after stop ({detail})")
    return DaemonStatus(running=False, detail=detail)


def _start_background(profile: str | None = None, debug: bool = False) -> DaemonStatus:
    cmd = [sys.executable, "-m", "tartarus_v2", "daemon"]
    if profile:
        cmd.extend(["--profile", profile])
    if debug:
        cmd.append("--debug")

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
        _clear_stale_pid()
        detail = f"daemon exited immediately code={proc.returncode}"
        reason = _recent_daemon_error()
        if reason:
            detail = f"{detail}: {reason}"
        return DaemonStatus(running=False, pid=proc.pid, detail=detail)
    return DaemonStatus(running=True, pid=proc.pid, detail="started (background)")


def _start_systemd() -> DaemonStatus:
    proc = _systemctl_user("start", USER_SERVICE)
    if proc is None:
        return DaemonStatus(running=False, detail="systemctl unavailable")
    for _ in range(25):
        if systemd_unit_active():
            return DaemonStatus(running=True, detail="started (systemd)")
        time.sleep(0.1)
    err = (proc.stderr or proc.stdout or "").strip()
    detail = f"systemd start failed ({err[:200] or proc.returncode})"
    reason = _recent_daemon_error()
    if reason:
        detail = f"{detail}: {reason}"
    return DaemonStatus(running=False, detail=detail)


def start(profile: str | None = None, debug: bool = False) -> DaemonStatus:
    """Start the remapper via systemd when enabled, else a background process."""
    current = status()
    if current.running:
        return DaemonStatus(
            running=True,
            pid=current.pid,
            detail="already running",
        )

    if systemd_unit_enabled():
        # Avoid a second remapper if a stale background pid lingered.
        _stop_pid_daemon(timeout=2.0)
        return _start_systemd()
    return _start_background(profile=profile, debug=debug)


def restart(profile: str | None = None, debug: bool = False) -> DaemonStatus:
    """Full stop of all supervisors, then start the preferred one.

    Used after package upgrades so an old in-memory remapper cannot linger
    beside a newly spawned process.
    """
    stop()
    time.sleep(0.4)
    if systemd_unit_enabled():
        # ``restart`` reloads the unit file and replaces the MainPID.
        proc = _systemctl_user("restart", USER_SERVICE)
        if proc is None:
            return DaemonStatus(running=False, detail="systemctl unavailable")
        for _ in range(30):
            if systemd_unit_active():
                return DaemonStatus(running=True, detail="restarted (systemd)")
            time.sleep(0.1)
        err = (proc.stderr or proc.stdout or "").strip()
        return DaemonStatus(
            running=False,
            detail=f"systemd restart failed ({err[:200] or proc.returncode})",
        )
    return _start_background(profile=profile, debug=debug)


def reload() -> DaemonStatus:
    """Ask a running daemon to re-read the active profile (SIGHUP)."""
    current = status()
    if not current.running:
        return DaemonStatus(running=False, detail="daemon not running")

    if current.pid is not None:
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
            _clear_stale_pid()
            return DaemonStatus(running=False, detail="daemon gone")
        except OSError as exc:
            return DaemonStatus(
                running=True,
                pid=current.pid,
                detail=f"reload failed: {exc}",
            )
        return DaemonStatus(running=True, pid=current.pid, detail="reload signaled")

    # systemd-managed: signal the unit's main process.
    proc = _systemctl_user("kill", "-s", "HUP", USER_SERVICE)
    if proc is None:
        return DaemonStatus(running=True, detail="reload skipped (no systemctl)")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return DaemonStatus(
            running=True,
            detail=f"reload failed ({err[:120] or proc.returncode})",
        )
    return DaemonStatus(running=True, detail="reload signaled (systemd)")
