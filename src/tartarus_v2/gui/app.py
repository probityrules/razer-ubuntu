"""GTK4 + Libadwaita application entry."""

from __future__ import annotations

import logging
import sys

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

    from tartarus_v2.gui.tray import attach_tray
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

    def on_quit(_action: Gio.SimpleAction, _param: None) -> None:
        app.quit()

    app.connect("activate", on_activate)

    about_action = Gio.SimpleAction.new("about", None)
    about_action.connect("activate", on_about)
    app.add_action(about_action)

    quit_action = Gio.SimpleAction.new("quit", None)
    quit_action.connect("activate", on_quit)
    app.add_action(quit_action)

    return app.run(None)
