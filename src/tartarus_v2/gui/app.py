"""GTK4 + Libadwaita application entry."""

from __future__ import annotations

import logging
import sys
from typing import Any

from tartarus_v2.gui.gi_check import GuiUnavailable, require_gi
from tartarus_v2.logging_util import setup_logging

log = logging.getLogger("tartarus_v2.gui")


def run_gui(debug: bool = False) -> int:
    setup_logging(debug=debug)
    try:
        require_gi()
    except GuiUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, Gtk

    from tartarus_v2.gui.report_issue import show_report_issue_dialog
    from tartarus_v2.gui.tray import attach_tray
    from tartarus_v2.gui.update_dialog import present_update_check
    from tartarus_v2.gui.window import create_main_window, show_about

    app = Adw.Application(application_id="com.tartarus_v2.app")
    app.debug = debug
    state: dict = {"window": None, "indicator": None}

    def on_activate(application: Adw.Application) -> None:
        if state["window"] is None:
            win = create_main_window(application, debug=debug)
            state["window"] = win

            def show() -> None:
                win.present()

            def quit_app() -> None:
                application.quit()

            state["indicator"] = attach_tray(
                application, win, on_show=show, on_quit=quit_app
            )
        state["window"].present()

    def on_about(_action: Gio.SimpleAction, _param: None) -> None:
        if state["window"] is not None:
            show_about(state["window"])

    def on_report_issue(_action: Gio.SimpleAction, _param: None) -> None:
        win = state["window"]
        if win is None:
            log.warning("Report issue: no window yet")
            return
        try:
            show_report_issue_dialog(win)
        except Exception as exc:  # noqa: BLE001
            log.exception("Report issue action failed")
            try:
                if getattr(win, "_toast_overlay", None):
                    win._toast_overlay.add_toast(Adw.Toast.new(f"Report issue failed: {exc}"))
            except Exception:  # noqa: BLE001
                pass

    def on_check_update(_action: Gio.SimpleAction, _param: None) -> None:
        win = state["window"]
        if win is None:
            log.warning("Check for updates: no window yet")
            return
        try:
            present_update_check(win)
        except Exception as exc:  # noqa: BLE001
            log.exception("Check for updates failed")
            try:
                if getattr(win, "_toast_overlay", None):
                    win._toast_overlay.add_toast(Adw.Toast.new(f"Update check failed: {exc}"))
            except Exception:  # noqa: BLE001
                pass

    def on_quit(_action: Gio.SimpleAction, _param: None) -> None:
        app.quit()

    def on_uninstall(_action: Gio.SimpleAction, _param: None) -> None:
        from tartarus_v2 import actions

        win = state["window"]
        if win is None:
            print(actions.uninstall_package())
            return

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
            result = actions.uninstall_package()
            if getattr(win, "_toast_overlay", None):
                win._toast_overlay.add_toast(Adw.Toast.new(result))
            if "removed" in result.lower():
                app.quit()

        dialog.connect("response", on_response)
        dialog.present(win)

    app.connect("activate", on_activate)

    about_action = Gio.SimpleAction.new("about", None)
    about_action.connect("activate", on_about)
    app.add_action(about_action)

    report_action = Gio.SimpleAction.new("report_issue", None)
    report_action.connect("activate", on_report_issue)
    app.add_action(report_action)

    update_action = Gio.SimpleAction.new("check_update", None)
    update_action.connect("activate", on_check_update)
    app.add_action(update_action)

    uninstall_action = Gio.SimpleAction.new("uninstall", None)
    uninstall_action.connect("activate", on_uninstall)
    app.add_action(uninstall_action)

    quit_action = Gio.SimpleAction.new("quit", None)
    quit_action.connect("activate", on_quit)
    app.add_action(quit_action)

    return app.run(None)
