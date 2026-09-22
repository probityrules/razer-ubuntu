"""XDG autostart helpers for the remap/lighting daemon."""

from __future__ import annotations

from pathlib import Path

AUTOSTART_BASENAME = "tartarus-v2-daemon.desktop"

DESKTOP_BODY = """\
[Desktop Entry]
Type=Application
Name=Tartarus V2 Daemon
Comment=Start Tartarus V2 lighting and remapper on login
Exec=tartarus-v2 daemon --background
Icon=input-keyboard
Terminal=false
X-GNOME-Autostart-enabled=true
NoDisplay=false
"""


def user_autostart_dir() -> Path:
    return Path.home() / ".config" / "autostart"


def user_autostart_path() -> Path:
    return user_autostart_dir() / AUTOSTART_BASENAME


def system_autostart_path() -> Path:
    return Path("/etc/xdg/autostart") / AUTOSTART_BASENAME


def is_autostart_enabled() -> bool:
    """True if login will start the daemon (user file wins over system)."""
    user = user_autostart_path()
    if user.exists():
        text = user.read_text(encoding="utf-8", errors="replace")
        if "Hidden=true" in text or "X-GNOME-Autostart-enabled=false" in text:
            return False
        return "X-GNOME-Autostart-enabled=true" in text or "Exec=" in text
    return system_autostart_path().exists()


def set_autostart_enabled(enabled: bool) -> Path:
    """Enable/disable user-level autostart (overrides packaged system entry)."""
    path = user_autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if enabled:
        path.write_text(DESKTOP_BODY, encoding="utf-8")
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
    return path
