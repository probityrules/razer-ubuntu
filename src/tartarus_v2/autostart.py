"""XDG autostart helpers for the remap/lighting daemon."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

AUTOSTART_BASENAME = "tartarus-v2-daemon.desktop"
SYSTEMD_USER_UNIT = "tartarus-v2.service"

# If the systemd user unit is enabled, it owns startup. This Exec then
# no-ops so login does not launch a second daemon.
DESKTOP_BODY = """\
[Desktop Entry]
Type=Application
Name=Tartarus V2 Daemon
Comment=Start Tartarus V2 lighting and remapper on login
Exec=sh -c 'if systemctl --user is-enabled --quiet tartarus-v2.service 2>/dev/null; then exit 0; fi; exec tartarus-v2 daemon --background'
Icon=input-keyboard
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
NoDisplay=false
"""


def user_autostart_dir() -> Path:
    return Path.home() / ".config" / "autostart"


def user_autostart_path() -> Path:
    return user_autostart_dir() / AUTOSTART_BASENAME


def system_autostart_path() -> Path:
    return Path("/etc/xdg/autostart") / AUTOSTART_BASENAME


def _systemd_unit_installed() -> bool:
    name = SYSTEMD_USER_UNIT
    return any(
        (root / name).exists()
        for root in (
            Path("/usr/lib/systemd/user"),
            Path("/lib/systemd/user"),
            Path("/etc/systemd/user"),
        )
    )


def _systemctl_user(*args: str) -> subprocess.CompletedProcess[str] | None:
    if not _systemd_unit_installed() or shutil.which("systemctl") is None:
        return None
    try:
        return subprocess.run(
            ["systemctl", "--user", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def systemd_user_enabled() -> bool:
    """True when the per-user tartarus-v2.service is enabled."""
    proc = _systemctl_user("is-enabled", "--quiet", SYSTEMD_USER_UNIT)
    return proc is not None and proc.returncode == 0


def _set_systemd_user_enabled(enabled: bool) -> None:
    _systemctl_user("enable" if enabled else "disable", "--now", SYSTEMD_USER_UNIT)


def xdg_autostart_enabled() -> bool:
    """True if an XDG autostart entry will launch the daemon."""
    user = user_autostart_path()
    if user.exists():
        text = user.read_text(encoding="utf-8", errors="replace")
        if "Hidden=true" in text or "X-GNOME-Autostart-enabled=false" in text:
            return False
        return "X-GNOME-Autostart-enabled=true" in text or "Exec=" in text
    return system_autostart_path().exists()


def is_autostart_enabled() -> bool:
    """True if login will start the daemon (systemd user unit or XDG)."""
    if systemd_user_enabled():
        return True
    return xdg_autostart_enabled()


def describe_autostart() -> str:
    """One-line status for diagnose dumps."""
    user = user_autostart_path()
    system = system_autostart_path()
    parts = [
        f"systemd_user_enabled={systemd_user_enabled()}",
        f"xdg_enabled={xdg_autostart_enabled()}",
        f"user_desktop={user} exists={user.exists()}",
        f"system_desktop={system} exists={system.exists()}",
    ]
    if user.exists():
        text = user.read_text(encoding="utf-8", errors="replace")
        if "Hidden=true" in text:
            parts.append("user_desktop_hidden=True")
    return " ".join(parts)


def set_autostart_enabled(enabled: bool) -> Path:
    """Enable/disable user-level autostart (overrides packaged system entry)."""
    path = user_autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if enabled:
        path.write_text(DESKTOP_BODY, encoding="utf-8")
        _set_systemd_user_enabled(True)
    else:
        # Same basename as system entry → XDG treats this as a disable override.
        path.write_text(
            DESKTOP_BODY.replace(
                "X-GNOME-Autostart-enabled=true",
                "X-GNOME-Autostart-enabled=false",
            )
            + "Hidden=true\n",
            encoding="utf-8",
        )
        _set_systemd_user_enabled(False)
    return path
