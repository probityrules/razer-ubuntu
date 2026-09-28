"""GI / Libadwaita availability checks."""

from __future__ import annotations

import sys


class GuiUnavailable(RuntimeError):
    pass


def require_gi() -> None:
    if sys.platform.startswith("win"):
        raise GuiUnavailable(
            "The Tartarus V2 GUI requires Linux (Ubuntu 26 / GNOME). "
            "Use the CLI on Windows, or run `tartarus-v2 gui` on the Ubuntu machine."
        )
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk  # noqa: F401
    except (ImportError, ValueError) as exc:
        raise GuiUnavailable(
            "GTK4 / Libadwaita (PyGObject) not available. On Ubuntu install:\n"
            "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1\n"
            f"Details: {exc}"
        ) from exc


def try_appindicator() -> bool:
    """Deprecated: Ayatana AppIndicator is GTK3-only and unused by the tray.

    Kept for callers/tests; always False so nothing tries to load GTK3 beside GTK4.
    """
    return False
