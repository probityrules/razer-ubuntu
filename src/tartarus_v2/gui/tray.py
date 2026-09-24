"""Ayatana / AppIndicator tray for daemon and profile quick actions."""

from __future__ import annotations

import logging
from typing import Any, Callable

from tartarus_v2.gui.controllers import DaemonController, ProfilesController
from tartarus_v2.gui.gi_check import try_appindicator

log = logging.getLogger("tartarus_v2.gui.tray")


class TrayController:
    """Menu action ids used by parity tests and the live indicator."""

    def __init__(self) -> None:
        self.daemon = DaemonController()
        self.profiles = ProfilesController()

    def show_window(self) -> str:
        return "show_window"

    def start_daemon(self, debug: bool = False) -> Any:
        return self.daemon.start_daemon(debug=debug)

    def stop_daemon(self) -> Any:
        return self.daemon.stop_daemon()

    def cycle_profile_next(self) -> str:
        from tartarus_v2.profiles import cycle_profile

        return cycle_profile("next")

    def check_for_update(self) -> Any:
        from tartarus_v2 import actions

        return actions.check_for_update()

    def uninstall(self) -> str:
        from tartarus_v2 import actions

        return actions.uninstall_package()

    def quit_app(self) -> str:
        return "quit"


def menu_action_ids() -> tuple[str, ...]:
    return (
        "show_window",
        "start_daemon",
        "stop_daemon",
        "cycle_profile_next",
        "check_for_update",
        "uninstall",
        "quit_app",
    )


def attach_tray(
    app: Any,
    window: Any,
    *,
    on_show: Callable[[], None],
    on_quit: Callable[[], None],
) -> Any | None:
    if not try_appindicator():
        log.info("AppIndicator not available; tray disabled")
        return None

    import gi

    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator
    except ValueError:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AppIndicator

    from gi.repository import Gtk

    ctrl = TrayController()
    indicator = AppIndicator.Indicator.new(
        "tartarus-v2",
        "input-keyboard",
        AppIndicator.IndicatorCategory.HARDWARE,
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

    menu = Gtk.Menu()

    def add_item(label: str, callback: Callable) -> None:
        item = Gtk.MenuItem(label=label)
        item.connect("activate", lambda *_: callback())
        menu.append(item)
        item.show()

    add_item("Show Tartarus V2", on_show)
    add_item("Start daemon", lambda: ctrl.start_daemon())
    add_item("Stop daemon", lambda: ctrl.stop_daemon())

    def next_profile() -> None:
        name = ctrl.cycle_profile_next()
        try:
            from gi.repository import Adw

            if getattr(window, "_toast_overlay", None):
                window._toast_overlay.add_toast(Adw.Toast.new(f"Profile: {name}"))
        except Exception:  # noqa: BLE001
            log.info("Switched profile to %s", name)

    add_item("Next profile", next_profile)

    def do_check_update() -> None:
        try:
            from tartarus_v2.gui.update_dialog import present_update_check

            present_update_check(window)
        except Exception as exc:  # noqa: BLE001
            log.warning("Check for updates failed: %s", exc)

    add_item("Check for updates…", do_check_update)

    def do_uninstall() -> None:
        # GTK3 MenuItem → use a simple confirm via print/log; GUI dialog needs GTK4 window.
        try:
            from gi.repository import Adw

            dialog = Adw.AlertDialog.new(
                "Uninstall Tartarus V2?",
                "This removes the tartarus-v2 package (requires admin). "
                "Profiles under ~/.cache/tartarus-v2 are kept.",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("uninstall", "Uninstall")
            dialog.set_response_appearance("uninstall", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")

            def on_response(_d: Any, response: str) -> None:
                if response != "uninstall":
                    return
                result = ctrl.uninstall()
                if getattr(window, "_toast_overlay", None):
                    window._toast_overlay.add_toast(Adw.Toast.new(result))
                if "removed" in result.lower():
                    on_quit()

            dialog.connect("response", on_response)
            dialog.present(window)
        except Exception as exc:  # noqa: BLE001
            log.warning("Uninstall dialog failed (%s); running directly", exc)
            result = ctrl.uninstall()
            log.info("%s", result)

    add_item("Uninstall…", do_uninstall)
    add_item("Quit", on_quit)
    menu.show_all()
    indicator.set_menu(menu)
    app._tray_controller = ctrl  # noqa: SLF001
    return indicator
