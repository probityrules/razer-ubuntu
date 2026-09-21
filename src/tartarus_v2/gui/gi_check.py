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
            "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 "
            "gir1.2-ayatanaappindicator3-0.1\n"
            f"Details: {exc}"
        ) from exc


def try_appindicator() -> bool:
    try:
        import gi

        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        try:
            import gi

            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False
