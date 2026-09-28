"""Detect / restart the Tartarus V2 GUI process (package upgrade helper)."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("tartarus_v2.gui_control")

# Env keys the GUI needs from the previous process (Wayland/X11 + session bus).
_SESSION_ENV_KEYS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "XDG_CURRENT_DESKTOP",
    "XDG_SESSION_TYPE",
    "XAUTHORITY",
)


@dataclass
class GuiStatus:
    running: bool
    pids: list[int]
    detail: str = ""


def _cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def _environ_map(pid: int) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for chunk in raw.split(b"\x00"):
        if not chunk or b"=" not in chunk:
            continue
        key, _, value = chunk.partition(b"=")
        try:
            out[key.decode("utf-8", errors="replace")] = value.decode(
                "utf-8", errors="replace"
            )
        except Exception:  # noqa: BLE001
            continue
    return out


def _looks_like_gui(cmdline: str) -> bool:
    """True for ``tartarus-v2 gui`` / ``python -m tartarus_v2 gui`` (not daemon)."""
    lower = cmdline.lower()
    if "tartarus" not in lower:
        return False
    if " daemon" in f" {lower}" or lower.endswith(" daemon"):
        return False
    # Avoid matching this helper itself when invoked as ``gui --restart``.
    if "--restart" in lower:
        return False
    parts = lower.split()
    if "gui" in parts:
        return True
    # Desktop entry / shebang wrappers sometimes put gui as the last token.
    return lower.rstrip().endswith(" gui")


def find_gui_pids(*, uid: int | None = None) -> list[int]:
    """Return PIDs of Tartarus GUI processes for ``uid`` (default: current user)."""
    want = os.getuid() if uid is None else int(uid)
    found: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return found
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            status = entry.joinpath("status").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        owner: int | None = None
        for line in status.splitlines():
            if line.startswith("Uid:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    owner = int(parts[1])
                break
        if owner != want:
            continue
        cmd = _cmdline(pid)
        if _looks_like_gui(cmd):
            found.append(pid)
    return sorted(found)


def status() -> GuiStatus:
    pids = find_gui_pids()
    if not pids:
        return GuiStatus(running=False, pids=[], detail="gui not running")
    return GuiStatus(
        running=True,
        pids=pids,
        detail=f"gui running (pid {', '.join(str(p) for p in pids)})",
    )


def _gui_command(*, debug: bool = False) -> list[str]:
    import shutil

    exe = shutil.which("tartarus-v2")
    if exe:
        cmd = [exe, "gui"]
    else:
        cmd = [sys.executable, "-m", "tartarus_v2", "gui"]
    if debug:
        cmd.append("--debug")
    return cmd


def _stop_pids(pids: list[int], *, timeout: float = 4.0) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except OSError as exc:
            log.debug("SIGTERM %s: %s", pid, exc)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        alive = [p for p in pids if _pid_alive(p)]
        if not alive:
            return
        time.sleep(0.1)
    for pid in pids:
        if not _pid_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
        except OSError as exc:
            log.debug("SIGKILL %s: %s", pid, exc)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def restart_if_running(*, debug: bool = False) -> GuiStatus:
    """If a GUI is open for this user, replace it with a fresh process.

    Used by package postinst so tray/UI upgrades apply without a manual relaunch.
    Does nothing when the GUI was not running (avoids popping a window after apt).
    """
    pids = find_gui_pids()
    if not pids:
        return GuiStatus(running=False, pids=[], detail="gui not running (left stopped)")

    session: dict[str, str] = {}
    for pid in pids:
        env = _environ_map(pid)
        for key in _SESSION_ENV_KEYS:
            if key in env and key not in session:
                session[key] = env[key]
        if session.get("DISPLAY") or session.get("WAYLAND_DISPLAY"):
            break

    _stop_pids(pids)

    child_env = os.environ.copy()
    child_env.update(session)
    if "XDG_RUNTIME_DIR" not in child_env:
        child_env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

    cmd = _gui_command(debug=debug)
    try:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            env=child_env,
        )
    except OSError as exc:
        return GuiStatus(
            running=False,
            pids=[],
            detail=f"stopped old gui but failed to relaunch: {exc}",
        )
    return GuiStatus(
        running=True,
        pids=[proc.pid],
        detail=f"gui restarted (pid {proc.pid})",
    )
