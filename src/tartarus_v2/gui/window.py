"""Main Libadwaita application window."""

from __future__ import annotations

from typing import Any

from tartarus_v2 import __version__
from tartarus_v2.gui.pages import (
    build_bindings_page,
    build_daemon_page,
    build_device_page,
    build_diagnose_page,
    build_lighting_page,
    build_profiles_page,
)


def create_main_window(app: Any, debug: bool = False) -> Any:
    from gi.repository import Adw, Gio, Gtk

    window = Adw.ApplicationWindow(application=app, title="Tartarus V2")
    window.set_default_size(920, 640)
    window.debug = debug

    toast_overlay = Adw.ToastOverlay()
    window._toast_overlay = toast_overlay  # noqa: SLF001

    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    toolbar.add_top_bar(header)

    split = Adw.NavigationSplitView()
    split.set_min_sidebar_width(200)

    sidebar_page = Adw.NavigationPage(title="Tartarus V2")
    sidebar_toolbar = Adw.ToolbarView()
    sidebar_header = Adw.HeaderBar()
    sidebar_toolbar.add_top_bar(sidebar_header)

    stack = Adw.ViewStack()
    stack.set_vexpand(True)

    pages = [
        ("device", "Device", "computer-symbolic", build_device_page),
        ("lighting", "Lighting", "weather-clear-symbolic", build_lighting_page),
        ("profiles", "Profiles", "folder-symbolic", build_profiles_page),
        ("bindings", "Bindings", "input-keyboard-symbolic", build_bindings_page),
        ("daemon", "Daemon", "system-run-symbolic", build_daemon_page),
        ("diagnose", "Diagnose", "dialog-information-symbolic", build_diagnose_page),
    ]
    for name, title, icon, builder in pages:
        page = builder(window)
        stack.add_titled_with_icon(page, name, title, icon)

    list_box = Gtk.ListBox()
    list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
    list_box.add_css_class("navigation-sidebar")
    row_by_name: dict[str, Any] = {}
    for name, title, icon, _ in pages:
        row = Adw.ActionRow(title=title)
        row.set_icon_name(icon)
        row._stack_name = name  # noqa: SLF001
        list_box.append(row)
        row_by_name[name] = row

    content_page = Adw.NavigationPage(title="Device")

    def _set_content_title_from_stack() -> None:
        child = stack.get_visible_child()
        if child is None:
            return
        page = stack.get_page(child)
        content_page.set_title(page.get_title() if page is not None else "Tartarus V2")

    def on_row_selected(_lb: Any, row: Any) -> None:
        if row is None:
            return
        name = getattr(row, "_stack_name", None)
        if name:
            stack.set_visible_child_name(name)
            _set_content_title_from_stack()

    list_box.connect("row-selected", on_row_selected)
    list_box.select_row(list_box.get_row_at_index(0))

    def navigate_to(name: str) -> None:
        row = row_by_name.get(name)
        if row is not None:
            list_box.select_row(row)
            return
        stack.set_visible_child_name(name)
        _set_content_title_from_stack()

    side_scroll = Gtk.ScrolledWindow(child=list_box)
    sidebar_toolbar.set_content(side_scroll)
    sidebar_page.set_child(sidebar_toolbar)

    content_toolbar = Adw.ToolbarView()
    content_header = Adw.HeaderBar()
    content_toolbar.add_top_bar(content_header)
    content_toolbar.set_content(stack)
    content_page.set_child(content_toolbar)

    split.set_sidebar(sidebar_page)
    split.set_content(content_page)

    # App menu
    menu = Gio.Menu()
    menu.append("Report issue…", "app.report_issue")
    menu.append("About Tartarus V2", "app.about")
    menu.append("Uninstall…", "app.uninstall")
    menu.append("Quit", "app.quit")
    menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
    menu_btn.set_menu_model(menu)
    content_header.pack_end(menu_btn)

    toast_overlay.set_child(split)
    window.set_content(toast_overlay)
    window._stack = stack  # noqa: SLF001
    window.navigate_to = navigate_to  # noqa: SLF001
    return window


def show_about(window: Any) -> None:
    from gi.repository import Adw

    dialog = Adw.AboutDialog(
        application_name="Tartarus V2",
        application_icon="input-keyboard",
        developer_name="tartarus-v2",
        version=__version__,
        comments="Standalone userspace driver for Razer Tartarus V2 on Ubuntu",
        license_type=1,  # MIT approx — use LICENSE_MIT if available
        website="https://github.com/",
    )
    try:
        from gi.repository import Gtk

        dialog.set_license_type(Gtk.License.MIT_X11)
    except Exception:  # noqa: BLE001
        pass
    dialog.present(window)
