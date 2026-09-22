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


def _error(window: Any, title: str, message: str) -> None:
    """Show a toast and an alert dialog for user-visible failures."""
    _toast(window, f"{title}: {message}")
    try:
        from gi.repository import Adw

        dialog = Adw.AlertDialog.new(title, message)
        dialog.add_response("ok", "OK")
        dialog.present(window)
    except Exception:  # noqa: BLE001
        pass


def _add_permissions_group(page: Any, window: Any, ctrl: DaemonController | None = None) -> None:
    """Banner + Fix button when input/plugdev membership is incomplete."""
    from gi.repository import Adw, Gtk

    daemon = ctrl or DaemonController()
    group = Adw.PreferencesGroup(title="Device access")
    status_row = Adw.ActionRow(title="Groups (input, plugdev)")
    fix_btn = Gtk.Button(label="Fix permissions")
    fix_btn.add_css_class("suggested-action")
    fix_row = Adw.ActionRow(
        title="Fix permissions",
        subtitle="Adds you to input+plugdev via polkit, then reload udev (log out required)",
    )
    fix_row.add_suffix(fix_btn)

    def refresh(_b: Any = None) -> None:
        st = daemon.permission_status()
        if st.ok:
            status_row.set_subtitle(st.detail)
            fix_btn.set_sensitive(False)
            fix_btn.set_label("OK")
        else:
            status_row.set_subtitle(st.detail)
            fix_btn.set_sensitive(True)
            fix_btn.set_label("Fix permissions")

    def do_fix(_b: Any = None) -> None:
        dialog = Adw.AlertDialog.new(
            "Fix device permissions?",
            "This asks for admin approval to add your user to the input and plugdev "
            "groups and reload udev rules. You must log out and back in afterward.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("fix", "Continue")
        dialog.set_response_appearance("fix", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("fix")
        dialog.set_close_response("cancel")

        def on_response(_d: Any, response: str) -> None:
            if response != "fix":
                return

            def work() -> str:
                return daemon.fix_permissions()

            def done(result: Any, error: BaseException | None) -> None:
                if error:
                    _toast(window, f"Fix failed: {error}")
                    return
                refresh()
                _toast(window, str(result))
                follow = Adw.AlertDialog.new("Almost done", str(result))
                follow.add_response("ok", "OK")
                follow.present(window)

            run_in_thread(work, done)

        dialog.connect("response", on_response)
        dialog.present(window)

    fix_btn.connect("clicked", do_fix)
    group.add(status_row)
    group.add(fix_row)
    page.add(group)
    refresh()


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
                _error(window, "Device error", str(error))
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
    _add_permissions_group(page, window)
    return page


def build_lighting_page(window: Any) -> Any:
    from gi.repository import Adw, Gdk, Gtk

    ctrl = LightingController()
    page = Adw.PreferencesPage(title="Lighting", name="lighting")
    group = Adw.PreferencesGroup(title="Effects", description="CLI: set-effect / set-brightness")

    effect_row = Adw.ComboRow(title="Effect")
    effect_row.set_model(Gtk.StringList.new(list(ctrl.list_effects())))
    effect_row.set_selected(2)

    def _rgba_from_hex(hex_rgb: str) -> Gdk.RGBA:
        text = hex_rgb.strip().lstrip("#")
        if len(text) != 6:
            text = "00FF00"
        rgba = Gdk.RGBA()
        rgba.red = int(text[0:2], 16) / 255.0
        rgba.green = int(text[2:4], 16) / 255.0
        rgba.blue = int(text[4:6], 16) / 255.0
        rgba.alpha = 1.0
        return rgba

    def _hex_from_rgba(rgba: Gdk.RGBA) -> str:
        return (
            f"{max(0, min(255, int(round(rgba.red * 255)))):02X}"
            f"{max(0, min(255, int(round(rgba.green * 255)))):02X}"
            f"{max(0, min(255, int(round(rgba.blue * 255)))):02X}"
        )

    color_dialog = Gtk.ColorDialog()
    color_dialog.set_with_alpha(False)
    color_dialog.set_title("Choose colour")

    primary = Gtk.ColorDialogButton.new(color_dialog)
    primary.set_rgba(_rgba_from_hex("00FF00"))
    primary.set_tooltip_text("Primary colour")
    rgb_row = Adw.ActionRow(title="Primary colour")
    rgb_row.add_suffix(primary)
    rgb_row.set_activatable_widget(primary)

    secondary = Gtk.ColorDialogButton.new(color_dialog)
    secondary.set_rgba(_rgba_from_hex("0000FF"))
    secondary.set_tooltip_text("Secondary colour (breath dual, etc.)")
    use_secondary = Gtk.Switch()
    use_secondary.set_valign(Gtk.Align.CENTER)
    rgb2_row = Adw.ActionRow(
        title="Secondary colour",
        subtitle="Enable for dual-colour effects (e.g. breath)",
    )
    rgb2_row.add_suffix(use_secondary)
    rgb2_row.add_suffix(secondary)
    rgb2_row.set_activatable_widget(use_secondary)

    def _sync_secondary_sensitive(*_args: Any) -> None:
        secondary.set_sensitive(use_secondary.get_active())

    use_secondary.connect("notify::active", _sync_secondary_sensitive)
    _sync_secondary_sensitive()

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

    from tartarus_v2.gui.controllers import ProfilesController

    profiles_ctrl = ProfilesController()
    save_switch = Gtk.Switch()
    save_switch.set_valign(Gtk.Align.CENTER)
    save_row = Adw.ActionRow(
        title="Save to profile",
        subtitle="Write lighting settings into the selected profile JSON",
    )
    save_row.add_suffix(save_switch)
    save_row.set_activatable_widget(save_switch)

    profile_list = Gtk.StringList()
    profile_row = Adw.ComboRow(title="Target profile")
    profile_row.set_model(profile_list)
    profile_row.set_sensitive(False)
    profile_names: list[str] = []

    def _reload_profiles(*_args: Any) -> None:
        nonlocal profile_names
        items = profiles_ctrl.refresh_profiles()
        n = profile_list.get_n_items()
        if n:
            profile_list.splice(0, n, [])
        profile_names = []
        active_idx = 0
        for i, item in enumerate(items):
            label = item["name"] + (" (active)" if item["active"] else "")
            profile_list.append(label)
            profile_names.append(item["name"])
            if item["active"]:
                active_idx = i
        if profile_names:
            profile_row.set_selected(active_idx)

    def _sync_save_sensitive(*_args: Any) -> None:
        profile_row.set_sensitive(save_switch.get_active())

    save_switch.connect("notify::active", _sync_save_sensitive)
    _reload_profiles()
    _sync_save_sensitive()

    refresh_profiles_btn = Gtk.Button(label="Refresh")
    refresh_profiles_btn.connect("clicked", _reload_profiles)
    refresh_profiles_row = Adw.ActionRow(title="Refresh profile list")
    refresh_profiles_row.add_suffix(refresh_profiles_btn)

    def _apply(_btn: Any = None) -> None:
        effect = ctrl.list_effects()[effect_row.get_selected()]
        rgb_hex = _hex_from_rgba(primary.get_rgba())
        rgb2_hex = (
            _hex_from_rgba(secondary.get_rgba()) if use_secondary.get_active() else None
        )
        target_profile = None
        if save_switch.get_active() and profile_names:
            idx = profile_row.get_selected()
            if 0 <= idx < len(profile_names):
                target_profile = profile_names[idx]

        def work() -> None:
            ctrl.apply_effect(
                effect,
                rgb=rgb_hex,
                rgb2=rgb2_hex,
                direction=int(direction.get_value()),
                speed=int(speed.get_value()),
                brightness=int(bright.get_value()),
                debug=getattr(window, "debug", False),
                save_to_profile=bool(target_profile),
                profile_name=target_profile,
            )

        def done(_result: Any, error: BaseException | None) -> None:
            if error:
                _error(window, "Lighting error", str(error))
            elif target_profile:
                _toast(window, f"Applied {effect} (saved to {target_profile})")
            else:
                _toast(window, f"Applied {effect}")

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
        profile_row,
        refresh_profiles_row,
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
        description="Activate a profile, or add a new one. Advanced tools are in the dialog below.",
    )

    state: dict[str, Any] = {"rows": []}

    def _clear_group() -> None:
        # Adw.PreferencesGroup has no clear(); remove known rows.
        for row in list(state["rows"]):
            group.remove(row)
        state["rows"] = []

    def _add_row(row: Any) -> None:
        group.add(row)
        state["rows"].append(row)

    def reload(_b: Any = None) -> None:
        _clear_group()
        for item in ctrl.refresh_profiles():
            name = item["name"]
            subtitle = "Active" if item["active"] else "Click to activate"
            row = Adw.ActionRow(title=name, subtitle=subtitle)
            if item["active"]:
                row.add_prefix(Gtk.Image.new_from_icon_name("object-select-symbolic"))
            row.set_activatable(True)

            def _activate(_row: Any, profile_name: str = name) -> None:
                try:
                    ctrl.activate_profile(profile_name)
                    reload()
                    _toast(window, f"Active: {profile_name} (daemon reloads if running)")
                except Exception as exc:  # noqa: BLE001
                    _error(window, "Could not activate profile", str(exc))

            row.connect("activated", _activate)
            _add_row(row)

        add_row = Adw.ActionRow(title="Add new…", subtitle="Clone the active profile")
        add_row.set_activatable(True)
        add_row.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))

        def _add(_row: Any = None) -> None:
            dialog = Adw.AlertDialog.new("New profile", "Name for the new profile:")
            entry = Gtk.Entry(placeholder_text="e.g. arena")
            entry.set_hexpand(True)
            dialog.set_extra_child(entry)
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("create", "Create")
            dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("create")
            dialog.set_close_response("cancel")

            def on_response(_d: Any, response: str) -> None:
                if response != "create":
                    return
                name = entry.get_text().strip()
                if not name:
                    _toast(window, "Enter a profile name")
                    return
                try:
                    ctrl.create_profile(name)
                except Exception as exc:  # noqa: BLE001
                    _error(window, "Could not create profile", str(exc))
                    return
                reload()
                _toast(window, f"Created {name}")

            dialog.connect("response", on_response)
            dialog.present(window)

        add_row.connect("activated", _add)
        _add_row(add_row)

    def open_advanced(_b: Any = None) -> None:
        dialog = Adw.PreferencesDialog(title="Advanced profiles")
        adv_page = Adw.PreferencesPage(title="Advanced")
        adv_group = Adw.PreferencesGroup(
            title="Tools",
            description="JSON preview, duplicate, and profile folder",
        )

        combo = Adw.ComboRow(title="Profile")
        string_list = Gtk.StringList()
        combo.set_model(string_list)
        names: list[str] = []

        def reload_combo() -> None:
            nonlocal names
            n = string_list.get_n_items()
            if n:
                string_list.splice(0, n, [])
            names = []
            active_idx = 0
            for i, item in enumerate(ctrl.refresh_profiles()):
                string_list.append(item["name"] + (" (active)" if item["active"] else ""))
                names.append(item["name"])
                if item["active"]:
                    active_idx = i
            if names:
                combo.set_selected(active_idx)

        def selected_name() -> str | None:
            idx = combo.get_selected()
            if 0 <= idx < len(names):
                return names[idx]
            return None

        def show_json(_b: Any = None) -> None:
            from tartarus_v2.actions import format_profile_json

            data = ctrl.show_profile(selected_name())
            alert = Adw.AlertDialog.new("Profile JSON", format_profile_json(data)[:4000])
            alert.add_response("ok", "OK")
            alert.present(window)

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
            try:
                ctrl.duplicate_profile(name, dest)
            except Exception as exc:  # noqa: BLE001
                _error(window, "Could not duplicate profile", str(exc))
                return
            reload_combo()
            reload()
            _toast(window, f"Created {dest}")

        adv_group.add(combo)
        for title, cb in (
            ("Show JSON", show_json),
            ("Duplicate", dup),
            ("Open folder", open_dir),
        ):
            row = Adw.ActionRow(title=title)
            b = Gtk.Button(label="Run")
            b.connect("clicked", cb)
            row.add_suffix(b)
            adv_group.add(row)

        adv_page.add(adv_group)
        dialog.add(adv_page)
        reload_combo()
        dialog.present(window)

    advanced_row = Adw.ActionRow(
        title="Advanced…",
        subtitle="JSON, duplicate, open folder",
    )
    adv_btn = Gtk.Button(label="Open")
    adv_btn.connect("clicked", open_advanced)
    advanced_row.add_suffix(adv_btn)

    page.add(group)
    bottom = Adw.PreferencesGroup()
    bottom.add(advanced_row)
    page.add(bottom)
    reload()
    return page


def build_bindings_page(window: Any) -> Any:
    from gi.repository import Adw, Gtk

    from tartarus_v2.gui.keymap import build_keymap_grid

    ctrl = BindingsController()
    profiles_ctrl = ProfilesController()
    keys = list(ALL_LOGICAL_KEYS)

    prefs = Adw.PreferencesPage(title="Bindings", name="bindings")
    group = Adw.PreferencesGroup(
        title="Edit binding",
        description="Pick Normal or Hypershift, select a key on the layout, then save.",
    )

    profile_list = Gtk.StringList()
    profile_row = Adw.ComboRow(title="Profile")
    profile_row.set_model(profile_list)
    profile_names: list[str] = []

    profiles_btn = Gtk.Button(label="Profiles")
    profiles_btn.set_tooltip_text("Open the Profiles tab")
    profiles_btn.add_css_class("flat")
    profile_row.add_suffix(profiles_btn)

    layer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    layer_box.add_css_class("linked")
    normal_btn = Gtk.ToggleButton(label="Normal")
    hs_btn = Gtk.ToggleButton(label="Hypershift")
    hs_btn.set_group(normal_btn)
    normal_btn.set_active(True)
    layer_box.append(normal_btn)
    layer_box.append(hs_btn)
    layer_mode_row = Adw.ActionRow(title="Layer")
    layer_mode_row.add_suffix(layer_box)

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
    state: dict[str, Any] = {"profile": None, "data": None, "layer": "standard"}
    suppress_profile: dict[str, bool] = {"busy": False}

    def current_layer() -> str:
        return "hypershift" if hs_btn.get_active() else "standard"

    def current_layer_label() -> str:
        return "Hypershift" if hs_btn.get_active() else "Normal"

    def _select_physical(logical: str) -> None:
        if logical in keys:
            key_row.set_selected(keys.index(logical))
            data = state.get("data") or {}
            layer = current_layer()
            bindings = (data.get(layer) or {}).get("bindings") or {}
            value = bindings.get(logical)
            if isinstance(value, str):
                type_row.set_selected(0)
                binding_entry.set_text(value)
            elif isinstance(value, dict):
                kind = value.get("type", "key")
                if kind == "macro":
                    type_row.set_selected(1)
                    steps = value.get("steps") or []
                    tip = steps[0].get("tap", "") if steps and isinstance(steps[0], dict) else ""
                    binding_entry.set_text(str(tip))
                elif kind == "profile_next":
                    type_row.set_selected(2)
                    binding_entry.set_text("")
                elif kind == "profile_prev":
                    type_row.set_selected(3)
                    binding_entry.set_text("")
                else:
                    type_row.set_selected(0)
                    binding_entry.set_text("")
            else:
                binding_entry.set_text("")
            status.set_subtitle(f"Selected {logical} ({current_layer_label()})")

    keymap = build_keymap_grid(_select_physical, layer_label="Normal")

    def _sync_keymap_bindings() -> None:
        data = state.get("data") or {}
        layer = current_layer()
        bindings = (data.get(layer) or {}).get("bindings") or {}
        keymap._keymap_set_layer_label(current_layer_label())  # noqa: SLF001
        keymap._keymap_set_bindings(bindings)  # noqa: SLF001

    def _reload_profile_combo(*, prefer: str | None = None) -> None:
        nonlocal profile_names
        suppress_profile["busy"] = True
        try:
            items = profiles_ctrl.refresh_profiles()
            n = profile_list.get_n_items()
            if n:
                profile_list.splice(0, n, [])
            profile_names = []
            select_idx = 0
            for i, item in enumerate(items):
                label = item["name"] + (" (active)" if item["active"] else "")
                profile_list.append(label)
                profile_names.append(item["name"])
                if prefer and item["name"] == prefer:
                    select_idx = i
                elif prefer is None and item["active"]:
                    select_idx = i
            if profile_names:
                profile_row.set_selected(select_idx)
        finally:
            suppress_profile["busy"] = False

    def _load_named(name: str | None = None, *, toast: bool = True) -> None:
        try:
            data = ctrl.load_bindings(name)
            state["data"] = data
            state["profile"] = data.get("name")
            hs = data.get("hypershift_key", "mode")
            if hs in keys:
                hs_row.set_selected(keys.index(hs))
            _sync_keymap_bindings()
            status.set_subtitle(f"Loaded {state['profile']} · {current_layer_label()}")
            if toast:
                _toast(window, f"Loaded {state['profile']}")
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not load profile", str(exc))

    def _on_profile_selected(_row: Any = None, _pspec: Any = None) -> None:
        if suppress_profile["busy"]:
            return
        if not profile_names:
            return
        idx = profile_row.get_selected()
        if not (0 <= idx < len(profile_names)):
            return
        name = profile_names[idx]
        if state.get("profile") == name and state.get("data"):
            return
        try:
            profiles_ctrl.activate_profile(name)
            _load_named(name)
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not switch profile", str(exc))

    def _on_layer_toggled(_btn: Any = None) -> None:
        state["layer"] = current_layer()
        _sync_keymap_bindings()
        status.set_subtitle(
            f"{state.get('profile') or '—'} · {current_layer_label()}"
        )

    def _go_profiles(_b: Any = None) -> None:
        navigate = getattr(window, "navigate_to", None)
        if callable(navigate):
            navigate("profiles")
        else:
            _toast(window, "Open Profiles from the sidebar")

    def _save_key(_b: Any = None) -> None:
        try:
            if not state["profile"]:
                _load_named()
            logical = keys[key_row.get_selected()]
            btype = ["key", "macro", "profile_next", "profile_prev"][type_row.get_selected()]
            text = binding_entry.get_text().strip()
            if btype == "key":
                value: Any = text
            elif btype == "macro":
                value = {"type": "macro", "steps": [{"tap": text or "a"}]}
            else:
                value = {"type": btype}
            layer = current_layer()
            data = state["data"] or ctrl.load_bindings(state["profile"])
            bindings = dict((data.get(layer) or {}).get("bindings") or {})
            bindings[logical] = value
            hs_key = keys[hs_row.get_selected()]
            profile = state["profile"] or data["name"]
            state["data"] = ctrl.save_bindings(profile, layer, bindings, hs_key)
            state["profile"] = profile
            _sync_keymap_bindings()
            status.set_subtitle(f"Saved {logical} on {current_layer_label()}")
            _toast(window, f"Saved {logical} (daemon reloads if running)")
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not save binding", str(exc))

    def _set_hs(_b: Any = None) -> None:
        try:
            if not state["profile"]:
                _load_named()
            key = keys[hs_row.get_selected()]
            state["data"] = ctrl.set_hypershift_key(state["profile"], key)
            _toast(window, f"Hypershift key: {key} (daemon reloads if running)")
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not set Hypershift key", str(exc))

    profiles_btn.connect("clicked", _go_profiles)
    normal_btn.connect("toggled", _on_layer_toggled)
    hs_btn.connect("toggled", _on_layer_toggled)
    profile_row.connect("notify::selected", _on_profile_selected)

    for row in (profile_row, layer_mode_row, hs_row, key_row, type_row, bind_row, status):
        group.add(row)
    for title, cb in (
        ("Save binding", _save_key),
        ("Set Hypershift key", _set_hs),
    ):
        row = Adw.ActionRow(title=title)
        b = Gtk.Button(label="Run")
        if title.startswith("Save"):
            b.add_css_class("suggested-action")
        b.connect("clicked", cb)
        row.add_suffix(b)
        group.add(row)
    prefs.add(group)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.append(keymap)
    content.append(prefs)
    scroll.set_child(content)
    outer.append(scroll)

    _reload_profile_combo()
    if profile_names:
        _load_named(profile_names[profile_row.get_selected()], toast=False)
    return outer


def build_daemon_page(window: Any) -> Any:
    from gi.repository import Adw, Gtk

    ctrl = DaemonController()
    page = Adw.PreferencesPage(title="Daemon", name="daemon")
    _add_permissions_group(page, window, ctrl)

    group = Adw.PreferencesGroup(
        title="Remap daemon",
        description="CLI: tartarus-v2 daemon (subprocess)",
    )
    status_row = Adw.ActionRow(title="Status", subtitle="Unknown")
    debug_switch = Gtk.Switch()
    debug_row = Adw.ActionRow(title="Debug logging")
    debug_row.add_suffix(debug_switch)
    debug_row.set_activatable_widget(debug_switch)

    autostart_switch = Gtk.Switch()
    autostart_switch.set_valign(Gtk.Align.CENTER)
    autostart_row = Adw.ActionRow(
        title="Start at login",
        subtitle="Launch the daemon when you sign in (XDG autostart)",
    )
    autostart_row.add_suffix(autostart_switch)
    autostart_row.set_activatable_widget(autostart_switch)

    suppress_autostart = {"busy": False}

    def _sync_autostart_ui() -> None:
        suppress_autostart["busy"] = True
        try:
            autostart_switch.set_active(ctrl.is_autostart_enabled())
        finally:
            suppress_autostart["busy"] = False

    def _on_autostart(*_args: Any) -> None:
        if suppress_autostart["busy"]:
            return
        enabled = autostart_switch.get_active()
        path = ctrl.set_autostart_enabled(enabled)
        _toast(window, f"Autostart {'on' if enabled else 'off'} ({path.name})")

    autostart_switch.connect("notify::active", _on_autostart)

    def _refresh(_b: Any = None) -> None:
        st = ctrl.daemon_status()
        status_row.set_subtitle(
            f"Running (pid {st.pid})" if st.running else (st.detail or "Stopped")
        )
        _sync_autostart_ui()

    def _start(_b: Any = None) -> None:
        try:
            st = ctrl.start_daemon(debug=debug_switch.get_active())
            status_row.set_subtitle(st.detail + (f" pid={st.pid}" if st.pid else ""))
            if st.running:
                _toast(window, st.detail)
            else:
                _error(window, "Daemon did not start", st.detail)
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not start daemon", str(exc))

    def _stop(_b: Any = None) -> None:
        try:
            st = ctrl.stop_daemon()
            status_row.set_subtitle(st.detail)
            _toast(window, st.detail)
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not stop daemon", str(exc))

    group.add(status_row)
    group.add(debug_row)
    group.add(autostart_row)
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
                _error(window, "Diagnose failed", str(error))
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
