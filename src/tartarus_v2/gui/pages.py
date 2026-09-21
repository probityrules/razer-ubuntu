"""Libadwaita page builders."""

from __future__ import annotations

from typing import Any

from tartarus_v2.gui.controllers import (
    BindingsController,
    DaemonController,
    DeviceController,
    DiagnoseController,
    LightingController,
    ProfilesController,
)
from tartarus_v2.gui.workers import run_in_thread
from tartarus_v2.input.keys import ALL_LOGICAL_KEYS


def _toast(window: Any, message: str) -> None:
    try:
        from gi.repository import Adw

        toast = Adw.Toast.new(message)
        overlay = getattr(window, "_toast_overlay", None)
        if overlay is not None:
            overlay.add_toast(toast)
    except Exception:  # noqa: BLE001
        pass


def build_device_page(window: Any) -> Any:
    from gi.repository import Adw, Gtk

    ctrl = DeviceController()
    page = Adw.PreferencesPage(title="Device", name="device")
    group = Adw.PreferencesGroup(title="Tartarus V2", description="USB device info (CLI: info)")
    firmware = Adw.ActionRow(title="Firmware", subtitle="—")
    serial = Adw.ActionRow(title="Serial", subtitle="—")
    brightness = Adw.ActionRow(title="Brightness", subtitle="—")
    for row in (firmware, serial, brightness):
        group.add(row)

    def _refresh(_btn: Any = None) -> None:
        def work() -> dict:
            return ctrl.refresh_device(debug=getattr(window, "debug", False))

        def done(result: Any, error: BaseException | None) -> None:
            if error:
                _toast(window, f"Device error: {error}")
                return
            firmware.set_subtitle(str(result.get("firmware", "")))
            serial.set_subtitle(str(result.get("serial", "")))
            brightness.set_subtitle(str(result.get("brightness", "")))
            _toast(window, "Device info refreshed")

        run_in_thread(work, done)

    btn = Gtk.Button(label="Refresh")
    btn.add_css_class("suggested-action")
    btn.connect("clicked", _refresh)
    header = Adw.ActionRow(title="Actions")
    header.add_suffix(btn)
    group.add(header)
    page.add(group)
    return page


def build_lighting_page(window: Any) -> Any:
    from gi.repository import Adw, Gtk

    ctrl = LightingController()
    page = Adw.PreferencesPage(title="Lighting", name="lighting")
    group = Adw.PreferencesGroup(title="Effects", description="CLI: set-effect / set-brightness")

    effect_row = Adw.ComboRow(title="Effect")
    effect_row.set_model(Gtk.StringList.new(list(ctrl.list_effects())))
    effect_row.set_selected(2)

    rgb = Gtk.Entry(placeholder_text="RRGGBB", text="00FF00")
    rgb_row = Adw.ActionRow(title="Primary colour")
    rgb_row.add_suffix(rgb)

    rgb2 = Gtk.Entry(placeholder_text="RRGGBB optional")
    rgb2_row = Adw.ActionRow(title="Secondary colour")
    rgb2_row.add_suffix(rgb2)

    direction = Gtk.SpinButton.new_with_range(0, 2, 1)
    direction.set_value(1)
    dir_row = Adw.ActionRow(title="Wave direction")
    dir_row.add_suffix(direction)

    speed = Gtk.SpinButton.new_with_range(1, 4, 1)
    speed.set_value(2)
    speed_row = Adw.ActionRow(title="Speed")
    speed_row.add_suffix(speed)

    bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 1)
    bright.set_value(128)
    bright.set_hexpand(True)
    bright.set_draw_value(True)
    bright_row = Adw.ActionRow(title="Brightness")
    bright_row.add_suffix(bright)

    save_switch = Gtk.Switch()
    save_row = Adw.ActionRow(title="Save to active profile")
    save_row.add_suffix(save_switch)
    save_row.set_activatable_widget(save_switch)

    def _apply(_btn: Any = None) -> None:
        effect = ctrl.list_effects()[effect_row.get_selected()]

        def work() -> None:
            ctrl.apply_effect(
                effect,
                rgb=rgb.get_text().strip() or "00FF00",
                rgb2=(rgb2.get_text().strip() or None),
                direction=int(direction.get_value()),
                speed=int(speed.get_value()),
                brightness=int(bright.get_value()),
                debug=getattr(window, "debug", False),
                save_to_profile=save_switch.get_active(),
            )

        def done(_result: Any, error: BaseException | None) -> None:
            _toast(window, f"Lighting error: {error}" if error else f"Applied {effect}")

        run_in_thread(work, done)

    apply_btn = Gtk.Button(label="Apply")
    apply_btn.add_css_class("suggested-action")
    apply_btn.connect("clicked", _apply)
    apply_row = Adw.ActionRow(title="Apply effect")
    apply_row.add_suffix(apply_btn)

    for row in (
        effect_row,
        rgb_row,
        rgb2_row,
        dir_row,
        speed_row,
        bright_row,
        save_row,
        apply_row,
    ):
        group.add(row)
    page.add(group)
    return page


def build_profiles_page(window: Any) -> Any:
    from gi.repository import Adw, Gio, Gtk

    ctrl = ProfilesController()
    page = Adw.PreferencesPage(title="Profiles", name="profiles")
    group = Adw.PreferencesGroup(
        title="Profiles",
        description="CLI: profile list / show / use / path",
    )

    status_row = Adw.ActionRow(title="Status", subtitle="Click Refresh")
    combo = Adw.ComboRow(title="Profile")
    string_list = Gtk.StringList()
    combo.set_model(string_list)

    def reload(_b: Any = None) -> None:
        n = string_list.get_n_items()
        if n:
            string_list.splice(0, n, [])
        names = []
        for item in ctrl.refresh_profiles():
            string_list.append(item["name"] + (" (active)" if item["active"] else ""))
            names.append(item["name"])
        combo._names = names  # noqa: SLF001
        status_row.set_subtitle(f"{len(names)} profile(s)")

    def selected_name() -> str | None:
        names = getattr(combo, "_names", [])
        idx = combo.get_selected()
        if 0 <= idx < len(names):
            return names[idx]
        return None

    def activate(_b: Any = None) -> None:
        name = selected_name()
        if not name:
            return
        ctrl.activate_profile(name)
        reload()
        _toast(window, f"Active: {name}")

    def show_dialog(_b: Any = None) -> None:
        from tartarus_v2.actions import format_profile_json

        data = ctrl.show_profile(selected_name())
        dialog = Adw.AlertDialog.new("Profile JSON", format_profile_json(data)[:4000])
        dialog.add_response("ok", "OK")
        dialog.present(window)

    def open_dir(_b: Any = None) -> None:
        path = ctrl.open_profiles_dir()
        try:
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)
        except Exception:  # noqa: BLE001
            _toast(window, str(path))

    def dup(_b: Any = None) -> None:
        name = selected_name()
        if not name:
            return
        dest = f"{name}-copy"
        ctrl.duplicate_profile(name, dest)
        reload()
        _toast(window, f"Created {dest}")

    group.add(status_row)
    group.add(combo)
    for title, cb in (
        ("Refresh list", reload),
        ("Activate", activate),
        ("Show JSON", show_dialog),
        ("Duplicate", dup),
        ("Open folder", open_dir),
    ):
        row = Adw.ActionRow(title=title)
        b = Gtk.Button(label="Run")
        b.connect("clicked", cb)
        row.add_suffix(b)
        group.add(row)

    page.add(group)
    reload()
    return page


def build_bindings_page(window: Any) -> Any:
    from gi.repository import Adw, Gtk

    ctrl = BindingsController()
    page = Adw.PreferencesPage(title="Bindings", name="bindings")
    group = Adw.PreferencesGroup(
        title="Key map",
        description="Standard / Hypershift layers (CLI profile JSON)",
    )

    keys = list(ALL_LOGICAL_KEYS)
    layer_row = Adw.ComboRow(title="Layer")
    layer_row.set_model(Gtk.StringList.new(["standard", "hypershift"]))
    hs_row = Adw.ComboRow(title="Hypershift key")
    hs_row.set_model(Gtk.StringList.new(keys))
    key_row = Adw.ComboRow(title="Physical key")
    key_row.set_model(Gtk.StringList.new(keys))
    type_row = Adw.ComboRow(title="Binding type")
    type_row.set_model(Gtk.StringList.new(["key", "macro", "profile_next", "profile_prev"]))

    binding_entry = Gtk.Entry(placeholder_text="e.g. a  or  ctrl+c  or  F1")
    bind_row = Adw.ActionRow(title="Binding")
    bind_row.add_suffix(binding_entry)
    status = Adw.ActionRow(title="Status", subtitle="Load a profile layer to edit")
    state: dict[str, Any] = {"profile": None, "data": None}

    def _load(_b: Any = None) -> None:
        data = ctrl.load_bindings()
        state["data"] = data
        state["profile"] = data.get("name")
        hs = data.get("hypershift_key", "mode")
        if hs in keys:
            hs_row.set_selected(keys.index(hs))
        status.set_subtitle(f"Loaded profile {state['profile']}")
        _toast(window, f"Loaded {state['profile']}")

    def _save_key(_b: Any = None) -> None:
        if not state["profile"]:
            _load()
        logical = keys[key_row.get_selected()]
        btype = ["key", "macro", "profile_next", "profile_prev"][type_row.get_selected()]
        text = binding_entry.get_text().strip()
        if btype == "key":
            value: Any = text
        elif btype == "macro":
            value = {"type": "macro", "steps": [{"tap": text or "a"}]}
        else:
            value = {"type": btype}
        layer = ["standard", "hypershift"][layer_row.get_selected()]
        data = state["data"] or ctrl.load_bindings()
        bindings = dict((data.get(layer) or {}).get("bindings") or {})
        bindings[logical] = value
        hs_key = keys[hs_row.get_selected()]
        profile = state["profile"] or data["name"]
        state["data"] = ctrl.save_bindings(profile, layer, bindings, hs_key)
        state["profile"] = profile
        status.set_subtitle(f"Saved {logical} on {layer}")
        _toast(window, f"Saved {logical}")

    def _set_hs(_b: Any = None) -> None:
        if not state["profile"]:
            _load()
        key = keys[hs_row.get_selected()]
        state["data"] = ctrl.set_hypershift_key(state["profile"], key)
        _toast(window, f"Hypershift key: {key}")

    for row in (layer_row, hs_row, key_row, type_row, bind_row, status):
        group.add(row)
    for title, cb in (
        ("Load active profile", _load),
        ("Save binding", _save_key),
        ("Set Hypershift key", _set_hs),
    ):
        row = Adw.ActionRow(title=title)
        b = Gtk.Button(label="Run")
        b.connect("clicked", cb)
        row.add_suffix(b)
        group.add(row)
    page.add(group)
    return page


def build_daemon_page(window: Any) -> Any:
    from gi.repository import Adw, Gtk

    ctrl = DaemonController()
    page = Adw.PreferencesPage(title="Daemon", name="daemon")
    group = Adw.PreferencesGroup(
        title="Remap daemon",
        description="CLI: tartarus-v2 daemon (subprocess)",
    )
    status_row = Adw.ActionRow(title="Status", subtitle="Unknown")
    debug_switch = Gtk.Switch()
    debug_row = Adw.ActionRow(title="Debug logging")
    debug_row.add_suffix(debug_switch)
    debug_row.set_activatable_widget(debug_switch)

    def _refresh(_b: Any = None) -> None:
        st = ctrl.daemon_status()
        status_row.set_subtitle(
            f"Running (pid {st.pid})" if st.running else (st.detail or "Stopped")
        )

    def _start(_b: Any = None) -> None:
        st = ctrl.start_daemon(debug=debug_switch.get_active())
        status_row.set_subtitle(st.detail + (f" pid={st.pid}" if st.pid else ""))
        _toast(window, st.detail)

    def _stop(_b: Any = None) -> None:
        st = ctrl.stop_daemon()
        status_row.set_subtitle(st.detail)
        _toast(window, st.detail)

    group.add(status_row)
    group.add(debug_row)
    for title, cb in (("Refresh status", _refresh), ("Start", _start), ("Stop", _stop)):
        row = Adw.ActionRow(title=title)
        b = Gtk.Button(label="Run")
        b.connect("clicked", cb)
        row.add_suffix(b)
        group.add(row)
    page.add(group)
    _refresh()
    return page


def build_diagnose_page(window: Any) -> Any:
    from gi.repository import Adw, Gdk, Gtk

    ctrl = DiagnoseController()
    page = Adw.PreferencesPage(title="Diagnose", name="diagnose")
    group = Adw.PreferencesGroup(
        title="Remote debug dump",
        description="CLI: tartarus-v2 diagnose — paste between COPY banners",
    )

    skip = Gtk.Switch()
    skip_row = Adw.ActionRow(title="Skip USB probe")
    skip_row.add_suffix(skip)
    skip_row.set_activatable_widget(skip)

    listen = Gtk.SpinButton.new_with_range(0, 30, 1)
    listen_row = Adw.ActionRow(title="Listen seconds")
    listen_row.add_suffix(listen)

    out_entry = Gtk.Entry(text="~/tartarus-diagnose.log")
    out_row = Adw.ActionRow(title="Output file")
    out_row.add_suffix(out_entry)

    def _run(_b: Any = None) -> None:
        out = out_entry.get_text().strip() or None

        def work() -> str:
            return ctrl.run_diagnose(
                out=out,
                listen=float(listen.get_value()),
                skip_probe=skip.get_active(),
            )

        def done(result: Any, error: BaseException | None) -> None:
            if error:
                _toast(window, f"Diagnose failed: {error}")
                return
            _toast(window, "Diagnose complete")

        run_in_thread(work, done)

    def _copy(_b: Any = None) -> None:
        text = ctrl.copy_report()
        display = Gdk.Display.get_default()
        if display and text:
            display.get_clipboard().set(text)
        _toast(window, "Copied to clipboard" if text else "Run diagnose first")

    def _save(_b: Any = None) -> None:
        if not ctrl.last_report:
            _toast(window, "Run diagnose first")
            return
        saved = ctrl.save_report(out_entry.get_text().strip() or "~/tartarus-diagnose.log")
        _toast(window, f"Saved {saved}")

    def _preview(_b: Any = None) -> None:
        dialog = Gtk.Window(title="Diagnose report", transient_for=window, modal=True)
        dialog.set_default_size(700, 500)
        tv = Gtk.TextView(editable=False, monospace=True)
        tv.get_buffer().set_text(ctrl.last_report or "")
        dialog.set_child(Gtk.ScrolledWindow(child=tv))
        dialog.present()

    for row in (skip_row, listen_row, out_row):
        group.add(row)
    for title, cb, suggested in (
        ("Run diagnose", _run, True),
        ("Copy report", _copy, False),
        ("Save report", _save, False),
        ("Open preview", _preview, False),
    ):
        row = Adw.ActionRow(title=title)
        b = Gtk.Button(label="Run")
        if suggested:
            b.add_css_class("suggested-action")
        b.connect("clicked", cb)
        row.add_suffix(b)
        group.add(row)

    page.add(group)
    return page
