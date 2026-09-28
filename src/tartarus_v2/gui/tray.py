"""StatusNotifierItem tray for daemon and profile quick actions (GTK4-safe).

Ayatana AppIndicator is GTK3-only and cannot load beside Libadwaita/GTK4 in the
same process. This module speaks the StatusNotifierItem + dbusmenu D-Bus APIs
directly via Gio so the panel label and menu work without Ayatana.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from tartarus_v2.gui.controllers import DaemonController, ProfilesController

log = logging.getLogger("tartarus_v2.gui.tray")

# Guide string so the panel reserves a stable width for the profile label.
_LABEL_GUIDE = "WWWWWWWWWWWWWWWW"

_SNI_PATH = "/StatusNotifierItem"
_MENU_PATH = "/MenuBar"

_SNI_XML = """
<node>
  <interface name='org.kde.StatusNotifierItem'>
    <property name='Category' type='s' access='read'/>
    <property name='Id' type='s' access='read'/>
    <property name='Title' type='s' access='read'/>
    <property name='Status' type='s' access='read'/>
    <property name='WindowId' type='u' access='read'/>
    <property name='IconName' type='s' access='read'/>
    <property name='IconThemePath' type='s' access='read'/>
    <property name='ItemIsMenu' type='b' access='read'/>
    <property name='Menu' type='o' access='read'/>
    <property name='ToolTip' type='(sa(iiay)ss)' access='read'/>
    <property name='XAyatanaLabel' type='s' access='read'/>
    <property name='XAyatanaLabelGuide' type='s' access='read'/>
    <method name='ContextMenu'>
      <arg type='i' name='x' direction='in'/>
      <arg type='i' name='y' direction='in'/>
    </method>
    <method name='Activate'>
      <arg type='i' name='x' direction='in'/>
      <arg type='i' name='y' direction='in'/>
    </method>
    <method name='SecondaryActivate'>
      <arg type='i' name='x' direction='in'/>
      <arg type='i' name='y' direction='in'/>
    </method>
    <method name='Scroll'>
      <arg type='i' name='delta' direction='in'/>
      <arg type='s' name='orientation' direction='in'/>
    </method>
    <signal name='NewTitle'/>
    <signal name='NewIcon'/>
    <signal name='NewToolTip'/>
    <signal name='NewStatus'>
      <arg type='s' name='status'/>
    </signal>
    <signal name='XAyatanaNewLabel'>
      <arg type='s' name='label'/>
      <arg type='s' name='guide'/>
    </signal>
  </interface>
</node>
"""

_DBUSMENU_XML = """
<node>
  <interface name='com.canonical.dbusmenu'>
    <property name='Version' type='u' access='read'/>
    <property name='Status' type='s' access='read'/>
    <property name='TextDirection' type='s' access='read'/>
    <property name='IconThemePath' type='as' access='read'/>
    <method name='GetLayout'>
      <arg type='i' name='parentId' direction='in'/>
      <arg type='i' name='recursionDepth' direction='in'/>
      <arg type='as' name='propertyNames' direction='in'/>
      <arg type='u' name='revision' direction='out'/>
      <arg type='(ia{sv}av)' name='layout' direction='out'/>
    </method>
    <method name='GetGroupProperties'>
      <arg type='ai' name='ids' direction='in'/>
      <arg type='as' name='propertyNames' direction='in'/>
      <arg type='a(ia{sv})' name='properties' direction='out'/>
    </method>
    <method name='GetProperty'>
      <arg type='i' name='id' direction='in'/>
      <arg type='s' name='name' direction='in'/>
      <arg type='v' name='value' direction='out'/>
    </method>
    <method name='Event'>
      <arg type='i' name='id' direction='in'/>
      <arg type='s' name='eventId' direction='in'/>
      <arg type='v' name='data' direction='in'/>
      <arg type='u' name='timestamp' direction='in'/>
    </method>
    <method name='AboutToShow'>
      <arg type='i' name='id' direction='in'/>
      <arg type='b' name='needUpdate' direction='out'/>
    </method>
    <signal name='LayoutUpdated'>
      <arg type='u' name='revision'/>
      <arg type='i' name='parent'/>
    </signal>
    <signal name='ItemsPropertiesUpdated'>
      <arg type='a(ia{sv})' name='updatedProps'/>
      <arg type='a(ias)' name='removedProps'/>
    </signal>
  </interface>
</node>
"""


def tray_status_text(*, profile: str | None, daemon_running: bool) -> tuple[str, str]:
    """Return (panel_label, tooltip) for the tray indicator.

    The panel label is the active profile name (language-indicator style).
    Tooltip carries daemon state for hosts that hide the label.
    """
    name = (profile or "").strip() or "—"
    label = name if len(name) <= 16 else name[:15] + "…"
    state = "ON" if daemon_running else "OFF"
    tip = f"Tartarus V2 · profile {name} · remap {state}"
    return label, tip


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
        from tartarus_v2 import actions

        return actions.cycle_active_profile("next")

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


def _variant(value: Any, sig: str) -> Any:
    from gi.repository import GLib

    return GLib.Variant(sig, value)


def _sv(text: str) -> Any:
    from gi.repository import GLib

    return GLib.Variant("s", text)


class _StatusNotifierTray:
    """Session-bus StatusNotifierItem with a dbusmenu."""

    def __init__(
        self,
        *,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        ctrl: TrayController,
        window: Any,
    ) -> None:
        from gi.repository import Gio, GLib

        self._on_show = on_show
        self._on_quit = on_quit
        self._ctrl = ctrl
        self._window = window
        self._Gio = Gio
        self._GLib = GLib

        self._label = "—"
        self._tooltip = "Tartarus V2"
        self._status_line = "Profile: —"
        self._conn: Any = None
        self._bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._own_id = 0
        self._sni_reg = 0
        self._menu_reg = 0
        self._menu_rev = 1
        self._actions: dict[int, Callable[[], None]] = {}
        self._items: list[tuple[int, dict[str, Any]]] = []

        self._rebuild_menu_items()
        self._own_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            self._bus_name,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            self._on_name_acquired,
            self._on_name_lost,
        )

    def _rebuild_menu_items(self) -> None:
        """Flat dbusmenu entries (id ≥ 1); id 0 is the root."""
        items: list[tuple[int, dict[str, Any]]] = []
        actions: dict[int, Callable[[], None]] = {}
        nid = 1

        def add(label: str, callback: Callable[[], None], *, enabled: bool = True) -> None:
            nonlocal nid
            items.append(
                (
                    nid,
                    {
                        "label": label,
                        "type": "standard",
                        "enabled": enabled,
                    },
                )
            )
            actions[nid] = callback
            nid += 1

        def sep() -> None:
            nonlocal nid
            items.append((nid, {"type": "separator"}))
            nid += 1

        add(self._status_line, lambda: None, enabled=False)
        sep()
        add("Show Tartarus V2", self._on_show)
        add("Start daemon", self._start_daemon)
        add("Stop daemon", self._stop_daemon)
        add("Next profile", self._next_profile)
        sep()
        add("Check for updates…", self._check_update)
        add("Uninstall…", self._uninstall)
        add("Quit", self._on_quit)

        self._items = items
        self._actions = actions

    def _start_daemon(self) -> None:
        self._ctrl.start_daemon()
        refresh = getattr(self._window, "refresh_header_daemon", None)
        if callable(refresh):
            refresh()
        else:
            self.refresh()

    def _stop_daemon(self) -> None:
        self._ctrl.stop_daemon()
        refresh = getattr(self._window, "refresh_header_daemon", None)
        if callable(refresh):
            refresh()
        else:
            self.refresh()

    def _next_profile(self) -> None:
        name = self._ctrl.cycle_profile_next()
        refresh = getattr(self._window, "refresh_header_daemon", None)
        if callable(refresh):
            refresh()
        else:
            self.refresh()
        try:
            from gi.repository import Adw

            if getattr(self._window, "_toast_overlay", None):
                self._window._toast_overlay.add_toast(Adw.Toast.new(f"Profile: {name}"))
        except Exception:  # noqa: BLE001
            log.info("Switched profile to %s", name)

    def _check_update(self) -> None:
        try:
            from tartarus_v2.gui.update_dialog import present_update_check

            present_update_check(self._window)
        except Exception as exc:  # noqa: BLE001
            log.warning("Check for updates failed: %s", exc)

    def _uninstall(self) -> None:
        try:
            from gi.repository import Adw

            dialog = Adw.AlertDialog.new(
                "Uninstall Tartarus V2?",
                "This removes the tartarus-v2 package (requires admin). "
                "Profiles under ~/.cache/tartarus-v2 are kept.",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("uninstall", "Uninstall")
            dialog.set_response_appearance(
                "uninstall", Adw.ResponseAppearance.DESTRUCTIVE
            )
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")

            def on_response(_d: Any, response: str) -> None:
                if response != "uninstall":
                    return
                result = self._ctrl.uninstall()
                if getattr(self._window, "_toast_overlay", None):
                    self._window._toast_overlay.add_toast(Adw.Toast.new(result))
                if "removed" in result.lower():
                    self._on_quit()

            dialog.connect("response", on_response)
            dialog.present(self._window)
        except Exception as exc:  # noqa: BLE001
            log.warning("Uninstall dialog failed (%s); running directly", exc)
            result = self._ctrl.uninstall()
            log.info("%s", result)

    def _on_bus_acquired(self, connection: Any, _name: str) -> None:
        self._conn = connection
        sni_node = self._Gio.DBusNodeInfo.new_for_xml(_SNI_XML)
        menu_node = self._Gio.DBusNodeInfo.new_for_xml(_DBUSMENU_XML)
        self._sni_reg = connection.register_object(
            _SNI_PATH,
            sni_node.interfaces[0],
            self._sni_method,
            self._sni_get_property,
            None,
        )
        self._menu_reg = connection.register_object(
            _MENU_PATH,
            menu_node.interfaces[0],
            self._menu_method,
            self._menu_get_property,
            None,
        )

    def _on_name_acquired(self, connection: Any, _name: str) -> None:
        self._register_with_watcher(connection)

    def _on_name_lost(self, _connection: Any, _name: str) -> None:
        log.warning("Lost StatusNotifierItem bus name %s", self._bus_name)

    def _register_with_watcher(self, connection: Any) -> None:
        try:
            connection.call(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                self._GLib.Variant("(s)", (self._bus_name,)),
                None,
                self._Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )
            log.info("Registered StatusNotifierItem (%s)", self._bus_name)
        except Exception as exc:  # noqa: BLE001
            # Watcher may appear later (panel restart); still export the item.
            log.warning("StatusNotifierWatcher register failed: %s", exc)

    def _emit_sni(self, signal: str, params: Any | None = None) -> None:
        if self._conn is None:
            return
        try:
            self._conn.emit_signal(
                None,
                _SNI_PATH,
                "org.kde.StatusNotifierItem",
                signal,
                params,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("SNI signal %s failed: %s", signal, exc)

    def _emit_menu_updated(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.emit_signal(
                None,
                _MENU_PATH,
                "com.canonical.dbusmenu",
                "LayoutUpdated",
                self._GLib.Variant("(ui)", (self._menu_rev, 0)),
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("dbusmenu LayoutUpdated failed: %s", exc)

    def refresh(self) -> None:
        try:
            from tartarus_v2.daemon_control import status as daemon_status
            from tartarus_v2.profiles import get_active_profile_name

            name = get_active_profile_name()
            running = bool(daemon_status().running)
        except Exception as exc:  # noqa: BLE001
            log.debug("Tray status refresh failed: %s", exc)
            name = "—"
            running = False
        label, tip = tray_status_text(profile=name, daemon_running=running)
        self._label = label
        self._tooltip = tip
        self._status_line = f"Profile: {name} · daemon {'ON' if running else 'OFF'}"
        self._rebuild_menu_items()
        self._menu_rev += 1
        self._emit_sni("NewTitle")
        self._emit_sni("NewToolTip")
        self._emit_sni(
            "XAyatanaNewLabel",
            self._GLib.Variant("(ss)", (self._label, _LABEL_GUIDE)),
        )
        self._emit_menu_updated()

    def _tooltip_variant(self) -> Any:
        # (icon_name, icon_pixmap[], title, description)
        return _variant(("", [], self._tooltip, ""), "(sa(iiay)ss)")

    def _sni_get_property(
        self,
        _conn: Any,
        _sender: Any,
        _path: Any,
        _iface: Any,
        prop: str,
    ) -> Any:
        if prop == "Category":
            return _sv("Hardware")
        if prop == "Id":
            return _sv("tartarus-v2")
        if prop == "Title":
            return _sv(self._tooltip)
        if prop == "Status":
            return _sv("Active")
        if prop == "WindowId":
            return _variant(0, "u")
        if prop == "IconName":
            return _sv("input-keyboard")
        if prop == "IconThemePath":
            return _sv("")
        if prop == "ItemIsMenu":
            return _variant(True, "b")
        if prop == "Menu":
            return _variant(_MENU_PATH, "o")
        if prop == "ToolTip":
            return self._tooltip_variant()
        if prop == "XAyatanaLabel":
            return _sv(self._label)
        if prop == "XAyatanaLabelGuide":
            return _sv(_LABEL_GUIDE)
        return None

    def _sni_method(
        self,
        _conn: Any,
        _sender: Any,
        _path: Any,
        _iface: Any,
        method: str,
        _params: Any,
        invocation: Any,
    ) -> None:
        if method in ("Activate", "SecondaryActivate"):
            self._on_show()
            invocation.return_value(None)
            return
        if method in ("ContextMenu", "Scroll"):
            # Menu is shown by the host via the Menu property; Scroll ignored.
            invocation.return_value(None)
            return
        invocation.return_error_literal(
            self._Gio.dbus_error_quark(),
            self._Gio.DBusError.UNKNOWN_METHOD,
            f"unknown method {method}",
        )

    def _props_for(self, item_id: int, names: list[str] | None = None) -> dict[str, Any]:
        props = {"enabled": _variant(True, "b"), "visible": _variant(True, "b")}
        for iid, raw in self._items:
            if iid != item_id:
                continue
            props["type"] = _sv(str(raw.get("type", "standard")))
            if "label" in raw:
                props["label"] = _sv(str(raw["label"]))
            if "enabled" in raw:
                props["enabled"] = _variant(bool(raw["enabled"]), "b")
            break
        if names:
            return {k: v for k, v in props.items() if k in names}
        return props

    def _layout_node(self, item_id: int) -> Any:
        from gi.repository import GLib

        children: list[Any] = []
        if item_id == 0:
            for iid, _raw in self._items:
                children.append(GLib.Variant("(ia{sv}av)", self._layout_tuple(iid)))
            props = {"children-display": _sv("submenu")}
            return (0, props, children)
        return self._layout_tuple(item_id)

    def _layout_tuple(self, item_id: int) -> tuple[int, dict[str, Any], list[Any]]:
        return (item_id, self._props_for(item_id), [])

    def _menu_get_property(
        self,
        _conn: Any,
        _sender: Any,
        _path: Any,
        _iface: Any,
        prop: str,
    ) -> Any:
        if prop == "Version":
            return _variant(3, "u")
        if prop == "Status":
            return _sv("normal")
        if prop == "TextDirection":
            return _sv("ltr")
        if prop == "IconThemePath":
            return _variant([], "as")
        return None

    def _menu_method(
        self,
        _conn: Any,
        _sender: Any,
        _path: Any,
        _iface: Any,
        method: str,
        params: Any,
        invocation: Any,
    ) -> None:
        GLib = self._GLib
        if method == "GetLayout":
            parent_id = int(params[0])
            layout = self._layout_node(parent_id)
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self._menu_rev, layout)))
            return
        if method == "GetGroupProperties":
            ids = list(params[0])
            names = list(params[1]) if params[1] is not None else []
            out = []
            for iid in ids:
                props = self._props_for(int(iid), names or None)
                if props:
                    out.append((int(iid), props))
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (out,)))
            return
        if method == "GetProperty":
            iid = int(params[0])
            name = str(params[1])
            props = self._props_for(iid, [name])
            if name not in props:
                invocation.return_error_literal(
                    self._Gio.dbus_error_quark(),
                    self._Gio.DBusError.INVALID_ARGS,
                    f"no property {name}",
                )
                return
            invocation.return_value(GLib.Variant("(v)", (props[name],)))
            return
        if method == "Event":
            iid = int(params[0])
            event_id = str(params[1])
            if event_id == "clicked":
                enabled = True
                for mid, raw in self._items:
                    if mid == iid:
                        enabled = bool(raw.get("enabled", True))
                        break
                if enabled:
                    cb = self._actions.get(iid)
                    if cb is not None:
                        try:
                            cb()
                        except Exception as exc:  # noqa: BLE001
                            log.warning("Tray menu action %s failed: %s", iid, exc)
            invocation.return_value(None)
            return
        if method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
            return
        invocation.return_error_literal(
            self._Gio.dbus_error_quark(),
            self._Gio.DBusError.UNKNOWN_METHOD,
            f"unknown method {method}",
        )

    def close(self) -> None:
        if self._conn is not None:
            if self._sni_reg:
                try:
                    self._conn.unregister_object(self._sni_reg)
                except Exception:  # noqa: BLE001
                    pass
            if self._menu_reg:
                try:
                    self._conn.unregister_object(self._menu_reg)
                except Exception:  # noqa: BLE001
                    pass
        if self._own_id:
            try:
                self._Gio.bus_unown_name(self._own_id)
            except Exception:  # noqa: BLE001
                pass
            self._own_id = 0


def attach_tray(
    app: Any,
    window: Any,
    *,
    on_show: Callable[[], None],
    on_quit: Callable[[], None],
) -> Any | None:
    """Attach a StatusNotifierItem tray; return the tray object or None."""
    try:
        from gi.repository import Gio  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        log.info("Gio not available; tray disabled (%s)", exc)
        return None

    ctrl = TrayController()
    try:
        tray = _StatusNotifierTray(
            on_show=on_show,
            on_quit=on_quit,
            ctrl=ctrl,
            window=window,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("StatusNotifierItem tray failed; tray disabled (%s)", exc)
        return None

    prev_refresh = getattr(window, "refresh_header_daemon", None)

    def refresh_header_and_tray() -> None:
        if callable(prev_refresh):
            prev_refresh()
        tray.refresh()

    window.refresh_header_daemon = refresh_header_and_tray  # noqa: SLF001
    window.refresh_tray = tray.refresh  # noqa: SLF001
    tray.refresh()

    app._tray_controller = ctrl  # noqa: SLF001
    app._tray_indicator = tray  # noqa: SLF001
    return tray
