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
from tartarus_v2.input.keys import ALL_LOGICAL_KEYS, describe_logical


def _toast(window: Any, message: str) -> None:
    try:
        from gi.repository import Adw

        toast = Adw.Toast.new(message)
        overlay = getattr(window, "_toast_overlay", None)
        if overlay is not None:
            overlay.add_toast(toast)
    except Exception:  # noqa: BLE001
        pass


def _refresh_header_daemon(window: Any) -> None:
    """Refresh header LED + active profile label immediately."""
    refresh = getattr(window, "refresh_header_daemon", None)
    if callable(refresh):
        try:
            refresh()
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
    status_row = Adw.ActionRow(title="Groups and /dev/uinput")
    fix_btn = Gtk.Button(label="Fix permissions")
    fix_btn.add_css_class("suggested-action")
    fix_row = Adw.ActionRow(
        title="Fix permissions",
        subtitle="input+plugdev and /dev/uinput via polkit (the driver does not run as root)",
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
            "This asks for admin approval once to add your user to input and plugdev, "
            "allow /dev/uinput so remapped keys reach text editors, and reload udev. "
            "The remap daemon does not need to run as root. Log out and back in afterward.",
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
    from gi.repository import Adw, GLib, Gtk

    ctrl = DeviceController()
    page = Adw.PreferencesPage(title="Device", name="device")
    group = Adw.PreferencesGroup(
        title="Tartarus V2",
        description="USB device info (updates automatically while this page is open)",
    )
    firmware = Adw.ActionRow(title="Firmware", subtitle="—")
    serial = Adw.ActionRow(title="Serial", subtitle="—")
    brightness = Adw.ActionRow(title="Brightness", subtitle="—")
    for row in (firmware, serial, brightness):
        group.add(row)

    poll: dict[str, Any] = {"source": None, "busy": False}

    def _refresh(*, silent: bool = True) -> None:
        if poll["busy"]:
            return
        poll["busy"] = True

        def work() -> dict:
            return ctrl.refresh_device(debug=getattr(window, "debug", False))

        def done(result: Any, error: BaseException | None) -> None:
            poll["busy"] = False
            if error:
                firmware.set_subtitle("unavailable")
                serial.set_subtitle(str(error)[:80])
                brightness.set_subtitle("—")
                if not silent:
                    _error(window, "Device error", str(error))
                return
            firmware.set_subtitle(str(result.get("firmware", "")))
            serial.set_subtitle(str(result.get("serial", "")))
            brightness.set_subtitle(str(result.get("brightness", "")))
            if not silent:
                _toast(window, "Device info refreshed")

        run_in_thread(work, done)

    def _start_poll(_w: Any = None) -> None:
        _refresh(silent=True)
        if poll["source"] is None:
            poll["source"] = GLib.timeout_add_seconds(8, lambda: (_refresh(silent=True), True)[1])

    def _stop_poll(_w: Any = None) -> None:
        src = poll.get("source")
        if src is not None:
            GLib.source_remove(src)
            poll["source"] = None

    page.connect("map", _start_poll)
    page.connect("unmap", _stop_poll)
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
                    _refresh_header_daemon(window)
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
    from gi.repository import Adw, GLib, Gtk

    from tartarus_v2.gui.keymap import build_keymap_grid
    from tartarus_v2.key_listen import KeyHighlightMonitor

    ctrl = BindingsController()
    profiles_ctrl = ProfilesController()
    keys = list(ALL_LOGICAL_KEYS)

    prefs = Adw.PreferencesPage(title="Bindings", name="bindings")
    group = Adw.PreferencesGroup(
        title="Edit binding",
        description=(
            "Remaps are system-wide: the remap daemon exclusive-grabs the keypad "
            "and emits a virtual keyboard to every app — not only this window. "
            "If the daemon cannot write /dev/uinput it exits and text editors keep "
            "the default keys (root is not required; use Fix permissions). "
            "Key highlight here is a preview. Apply writes the profile; if the "
            "daemon is off it will be started so remaps take effect immediately."
        ),
    )

    profile_list = Gtk.StringList()
    profile_row = Adw.ComboRow(title="Profile")
    profile_row.set_model(profile_list)
    profile_names: list[str] = []

    profiles_btn = Gtk.Button(label="Profiles")
    profiles_btn.set_tooltip_text("Open the Profiles tab")
    profiles_btn.add_css_class("flat")
    profile_row.add_suffix(profiles_btn)

    hs_row = Adw.ComboRow(title="Hypershift key")
    hs_row.set_model(Gtk.StringList.new(keys))

    selected_row = Adw.ActionRow(title="Selected key", subtitle="Click a key on the layout")
    normal_entry = Gtk.Entry(placeholder_text="Normal binding, e.g. a  or  ctrl+c")
    normal_row = Adw.ActionRow(title="Normal")
    normal_row.add_suffix(normal_entry)
    hs_entry = Gtk.Entry(placeholder_text="Hypershift binding, e.g. F1")
    hs_entry_row = Adw.ActionRow(title="Hypershift")
    hs_entry_row.add_suffix(hs_entry)

    status = Adw.ActionRow(title="Status", subtitle="Load a profile to edit")
    listen_row = Adw.ActionRow(title="Key highlight", subtitle="Starting…")

    state: dict[str, Any] = {
        "profile": None,
        "draft": None,
        "baseline": None,
        "selected": None,
        "dirty": False,
        "suppress_entries": False,
    }
    suppress_profile: dict[str, bool] = {"busy": False}
    highlight: dict[str, Any] = {"monitor": None}

    apply_btn = Gtk.Button(label="Apply")
    apply_btn.add_css_class("suggested-action")
    apply_btn.set_sensitive(False)

    def _draft_bindings(layer: str) -> dict[str, Any]:
        data = state.get("draft") or {}
        return dict((data.get(layer) or {}).get("bindings") or {})

    def _set_dirty(dirty: bool) -> None:
        state["dirty"] = dirty
        apply_btn.set_sensitive(dirty)
        apply_btn.set_tooltip_text(
            "Save all draft bindings and run the system-wide remap daemon"
            if dirty
            else "No pending binding changes"
        )
        if dirty and state.get("profile"):
            status.set_subtitle(f"{state['profile']} · unpublished changes")

    def _sync_keymap() -> None:
        keymap._keymap_set_bindings(  # noqa: SLF001
            standard=_draft_bindings("standard"),
            hypershift=_draft_bindings("hypershift"),
        )
        mon = highlight.get("monitor")
        if mon is not None and state.get("draft"):
            mon.set_profile(state["draft"])

    def _fill_entries_for(logical: str | None) -> None:
        state["suppress_entries"] = True
        try:
            if not logical:
                selected_row.set_subtitle("Click a key on the layout")
                normal_entry.set_text("")
                hs_entry.set_text("")
                return
            selected_row.set_subtitle(describe_logical(logical))

            def _as_text(value: Any) -> str:
                if value is None:
                    return ""
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    kind = value.get("type", "key")
                    if kind == "macro":
                        steps = value.get("steps") or []
                        if steps and isinstance(steps[0], dict):
                            return str(steps[0].get("tap") or "")
                        return "macro"
                    if kind == "key":
                        return str(value.get("key") or value.get("keys") or "")
                    return str(kind)
                return str(value)

            normal_entry.set_text(_as_text(_draft_bindings("standard").get(logical)))
            hs_entry.set_text(_as_text(_draft_bindings("hypershift").get(logical)))
        finally:
            state["suppress_entries"] = False

    def _select_physical(logical: str) -> None:
        state["selected"] = logical
        keymap._keymap_set_selected(logical)  # noqa: SLF001
        _fill_entries_for(logical)
        status.set_subtitle(f"Editing {describe_logical(logical)}")

    keymap = build_keymap_grid(_select_physical)

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
        import copy

        try:
            from tartarus_v2.profiles import get_active_profile_name

            requested = name or get_active_profile_name()
            data = ctrl.load_bindings(requested)
            # Always key drafts by the filename/stem we asked for, not a stale JSON name.
            data["name"] = requested
            state["draft"] = copy.deepcopy(data)
            state["baseline"] = copy.deepcopy(data)
            state["profile"] = requested
            hs = data.get("hypershift_key", "mode")
            suppress_profile["busy"] = True
            try:
                if hs in keys:
                    hs_row.set_selected(keys.index(hs))
                else:
                    hs_row.set_selected(0)
            finally:
                suppress_profile["busy"] = False
            # Force keymap + entry fields to the newly loaded profile immediately.
            _sync_keymap()
            _fill_entries_for(state.get("selected"))
            _set_dirty(False)
            status.set_subtitle(f"Loaded {requested}")
            if toast:
                _toast(window, f"Loaded {requested}")
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not load profile", str(exc))

    def _switch_to_profile(name: str, *, toast: bool = True) -> None:
        """Activate + load + refresh UI for a profile (Bindings dropdown / page map)."""
        previous = state.get("profile")
        if state.get("dirty") and previous is not None and previous != name:
            _toast(window, "Discarded unpublished binding edits")
        profiles_ctrl.activate_profile(name)
        _load_named(name, toast=toast and previous != name)
        # Refresh "(active)" markers without re-entering via notify::selected.
        _reload_profile_combo(prefer=name)
        _refresh_header_daemon(window)
        # Highlight monitor must re-bind to the new profile map.
        _start_highlight()

    def _on_profile_selected(_row: Any = None, _pspec: Any = None) -> None:
        if suppress_profile["busy"]:
            return
        if not profile_names:
            return
        idx = profile_row.get_selected()
        if not (0 <= idx < len(profile_names)):
            return
        name = profile_names[idx]
        # Combo rebuild after activate re-fires notify — avoid a reload loop, but
        # still push the current draft onto the keymap if we are already on this profile.
        if state.get("profile") == name and state.get("draft") is not None and not state.get("dirty"):
            _sync_keymap()
            _fill_entries_for(state.get("selected"))
            _refresh_header_daemon(window)
            return
        try:
            _switch_to_profile(name, toast=True)
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not switch profile", str(exc))

    def _go_profiles(_b: Any = None) -> None:
        navigate = getattr(window, "navigate_to", None)
        if callable(navigate):
            navigate("profiles")
        else:
            _toast(window, "Open Profiles from the sidebar")

    def _stage_entry(layer: str, entry: Any) -> None:
        if state["suppress_entries"]:
            return
        logical = state.get("selected")
        if not logical or not state.get("draft"):
            return
        text = entry.get_text().strip()
        data = state["draft"]
        data.setdefault(layer, {})
        bindings = dict((data.get(layer) or {}).get("bindings") or {})
        if text:
            bindings[logical] = text
        else:
            bindings.pop(logical, None)
        data[layer]["bindings"] = bindings
        _sync_keymap()
        _set_dirty(True)

    def _on_normal_changed(_e: Any = None) -> None:
        _stage_entry("standard", normal_entry)

    def _on_hs_changed(_e: Any = None) -> None:
        _stage_entry("hypershift", hs_entry)

    def _on_hs_key(_row: Any = None, _pspec: Any = None) -> None:
        if suppress_profile["busy"]:
            return
        if not state.get("draft"):
            return
        key = keys[hs_row.get_selected()]
        if state["draft"].get("hypershift_key") == key:
            return
        state["draft"]["hypershift_key"] = key
        _set_dirty(True)

    def _apply(_b: Any = None) -> None:
        if not state.get("dirty") or not state.get("draft") or not state.get("profile"):
            return
        try:
            import copy

            from tartarus_v2.gui.controllers import DaemonController

            draft = state["draft"]
            profile = state["profile"]
            hs_key = draft.get("hypershift_key") or keys[hs_row.get_selected()]
            # Persist both layers + hypershift key in one shot.
            std = dict((draft.get("standard") or {}).get("bindings") or {})
            hyp = dict((draft.get("hypershift") or {}).get("bindings") or {})
            ctrl.save_bindings(profile, "standard", std, hs_key)
            data = ctrl.save_bindings(profile, "hypershift", hyp, hs_key)
            # Keep draft isolated from the returned (and any future) profile object.
            state["draft"] = copy.deepcopy(data)
            state["draft"]["name"] = profile
            state["baseline"] = copy.deepcopy(state["draft"])
            _set_dirty(False)

            daemon_ctrl = DaemonController()
            st = daemon_ctrl.daemon_status()
            if not st.running:
                # Bindings on disk do nothing until the system-wide remapper runs.
                st = daemon_ctrl.start_daemon()
                _refresh_header_daemon(window)
                if not st.running:
                    _error(
                        window,
                        "Bindings saved, but remap daemon did not start",
                        st.detail
                        + "\n\nWithout the daemon, keys stay stock HID everywhere "
                        "(the Bindings preview is not a system remapper). "
                        "Try Daemon → Start, or: tartarus-v2 fix-permissions",
                    )
                    status.set_subtitle("Saved — daemon not running (no system remap)")
                    _sync_keymap()
                    return
                _toast(
                    window,
                    "Applied — bindings saved; remap daemon started (system-wide)",
                )
                status.set_subtitle("Applied — daemon started (system-wide remap)")
            else:
                detail = ctrl.apply_bindings()
                _refresh_header_daemon(window)
                if "signaled" in detail.lower() or "reload" in detail.lower():
                    _toast(
                        window,
                        "Applied — bindings saved; daemon reloaded (system-wide)",
                    )
                else:
                    _toast(window, f"Applied ({detail})")
                status.set_subtitle(f"Applied ({detail})")
            _sync_keymap()
            _start_highlight()
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not apply bindings", str(exc))

    def _on_highlight(pressed: set[str], mode: str) -> None:
        def apply() -> bool:
            keymap._keymap_set_pressed(pressed)  # noqa: SLF001
            if mode == "physical":
                listen_row.set_subtitle("Physical EV_KEY (daemon off)")
            elif mode == "virtual":
                listen_row.set_subtitle("Mapped output (daemon on)")
            elif mode == "stopped":
                listen_row.set_subtitle("Idle")
            else:
                listen_row.set_subtitle(mode)
            return False

        GLib.idle_add(apply)

    def _start_highlight() -> None:
        mon = highlight.get("monitor")
        if mon is not None:
            mon.stop()
        mon = KeyHighlightMonitor(_on_highlight)
        if state.get("draft"):
            mon.set_profile(state["draft"])
        highlight["monitor"] = mon
        try:
            mon.start()
        except Exception as exc:  # noqa: BLE001
            listen_row.set_subtitle(f"Unavailable: {exc}")

    def _stop_highlight() -> None:
        mon = highlight.get("monitor")
        if mon is not None:
            mon.stop()
            highlight["monitor"] = None
        keymap._keymap_set_pressed(set())  # noqa: SLF001

    profiles_btn.connect("clicked", _go_profiles)
    profile_row.connect("notify::selected", _on_profile_selected)
    hs_row.connect("notify::selected", _on_hs_key)
    normal_entry.connect("changed", _on_normal_changed)
    hs_entry.connect("changed", _on_hs_changed)

    for row in (profile_row, hs_row, selected_row, normal_row, hs_entry_row, listen_row, status):
        group.add(row)

    apply_row = Adw.ActionRow(
        title="Apply all",
        subtitle="Save bindings and ensure the system-wide remap daemon is running",
    )
    apply_btn.connect("clicked", _apply)
    apply_row.add_suffix(apply_btn)
    group.add(apply_row)
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

    def _on_bindings_map(_w: Any = None) -> None:
        _reload_profile_combo()
        # Pick up activation done on the Profiles page.
        try:
            from tartarus_v2.profiles import get_active_profile_name

            active = get_active_profile_name()
            if state.get("dirty") and state.get("profile") == active and state.get("draft"):
                # Keep unpublished edits for the still-active profile.
                if active in profile_names:
                    suppress_profile["busy"] = True
                    try:
                        profile_row.set_selected(profile_names.index(active))
                    finally:
                        suppress_profile["busy"] = False
                _sync_keymap()
                _fill_entries_for(state.get("selected"))
                _start_highlight()
                _refresh_header_daemon(window)
                return
            _switch_to_profile(active, toast=False)
        except Exception:  # noqa: BLE001
            _start_highlight()

    outer.connect("map", _on_bindings_map)
    outer.connect("unmap", lambda *_: _stop_highlight())

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
        description=(
            "System-wide driver: exclusive-grabs the Tartarus and injects a "
            "virtual keyboard for every app. Opening this window is not enough — "
            "the header LED must stay green. LED grey means text editors still "
            "get the firmware default keys. The daemon does not need root; it "
            "needs a writable /dev/uinput (Fix permissions)."
        ),
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
            _refresh_header_daemon(window)
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
            _refresh_header_daemon(window)
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
    from gi.repository import Adw, Gdk, GLib, Gtk

    from tartarus_v2.gui.controllers import DaemonController

    ctrl = DiagnoseController()
    daemon_ctrl = DaemonController()
    page = Adw.PreferencesPage(title="Diagnose", name="diagnose")

    live = Adw.PreferencesGroup(
        title="Live key listen",
        description=(
            "Same source selection as Bindings key highlight. Use the remap "
            "daemon toggle to choose physical EV_KEY vs remapped virtual output."
        ),
    )

    daemon_switch = Gtk.Switch()
    daemon_row = Adw.ActionRow(title="Remap daemon")
    daemon_row.add_suffix(daemon_switch)
    daemon_row.set_activatable_widget(daemon_switch)

    live_status = Adw.ActionRow(title="Status", subtitle="Idle")
    pressed_label = Gtk.Label(
        label="(none)",
        xalign=0,
        wrap=True,
        selectable=True,
    )
    pressed_label.add_css_class("monospace")
    pressed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    pressed_box.set_margin_start(12)
    pressed_box.set_margin_end(12)
    pressed_box.set_margin_bottom(8)
    pressed_hdr = Gtk.Label(label="Currently pressed", xalign=0)
    pressed_hdr.add_css_class("heading")
    pressed_box.append(pressed_hdr)
    pressed_box.append(pressed_label)

    log_view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
    log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    log_buf = log_view.get_buffer()
    log_scroll = Gtk.ScrolledWindow()
    log_scroll.set_min_content_height(160)
    log_scroll.set_child(log_view)
    log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    log_box.set_margin_start(12)
    log_box.set_margin_end(12)
    log_box.set_margin_bottom(8)
    log_hdr = Gtk.Label(label="Recent events", xalign=0)
    log_hdr.add_css_class("heading")
    log_box.append(log_hdr)
    log_box.append(log_scroll)

    start_btn = Gtk.Button(label="Start listening")
    start_btn.add_css_class("suggested-action")
    stop_btn = Gtk.Button(label="Stop")
    stop_btn.set_sensitive(False)
    reload_btn = Gtk.Button(label="Reload profile")
    reload_btn.set_sensitive(False)

    listen_state: dict[str, Any] = {
        "active": False,
        "suppress_daemon": False,
        "daemon_busy": False,
        "restarting": False,
    }

    def _listen_explain(daemon_on: bool) -> str:
        if daemon_on:
            return (
                "On — listening to the virtual keyboard (bound / remapped output)."
            )
        return "Off — reporting physical Tartarus EV_KEY codes."

    def _prefer_mode() -> str:
        return "virtual" if daemon_switch.get_active() else "physical"

    def _sync_daemon_row(*, from_status: bool = False) -> None:
        if from_status:
            running = bool(daemon_ctrl.daemon_status().running)
            listen_state["suppress_daemon"] = True
            try:
                daemon_switch.set_active(running)
            finally:
                listen_state["suppress_daemon"] = False
        daemon_row.set_subtitle(_listen_explain(daemon_switch.get_active()))

    def _set_listening_ui(active: bool) -> None:
        listen_state["active"] = active
        start_btn.set_sensitive(not active)
        stop_btn.set_sensitive(active)
        reload_btn.set_sensitive(active)

    def _on_listen_update(payload: dict[str, Any]) -> None:
        def apply() -> bool:
            mode = payload.get("mode") or ""
            if mode == "physical":
                mode_txt = "physical EV_KEY"
            elif mode == "virtual":
                mode_txt = "virtual output"
            elif mode:
                mode_txt = str(mode)
            else:
                mode_txt = "—"
            hs = " · Hypershift ON" if payload.get("hypershift") else ""
            prof = payload.get("profile") or "—"
            live_status.set_subtitle(
                f"{payload.get('status', '')} · {mode_txt} · profile={prof}{hs}"
            )
            pressed = payload.get("pressed") or []
            pressed_label.set_label("\n".join(pressed) if pressed else "(none)")
            log_lines = payload.get("log") or []
            log_buf.set_text("\n".join(log_lines) if log_lines else "")
            status = str(payload.get("status", ""))
            if (
                not payload.get("running", True)
                and "Stopped" in status
                and listen_state["active"]
                and not listen_state["restarting"]
            ):
                _set_listening_ui(False)
                live_status.set_subtitle("Idle")
            return False

        GLib.idle_add(apply)

    def _begin_listen() -> None:
        try:
            prefer = _prefer_mode()
            ctrl.start_live_listen(_on_listen_update, prefer=prefer)
            _set_listening_ui(True)
            _toast(
                window,
                "Listening to remapped output"
                if prefer == "virtual"
                else "Listening to physical EV_KEY",
            )
        except Exception as exc:  # noqa: BLE001
            _set_listening_ui(False)
            _error(window, "Could not start key listen", str(exc))

    def _finish_listen(*, from_callback: bool = False) -> None:
        listen_state["restarting"] = False
        try:
            ctrl.stop_live_listen()
        except Exception as exc:  # noqa: BLE001
            if not from_callback:
                _error(window, "Could not stop key listen", str(exc))
        _set_listening_ui(False)
        live_status.set_subtitle("Idle")
        pressed_label.set_label("(none)")

    def _restart_listen_if_active() -> None:
        if not listen_state["active"]:
            return
        listen_state["restarting"] = True
        try:
            ctrl.stop_live_listen()
        except Exception:  # noqa: BLE001
            pass

        def restart() -> bool:
            listen_state["restarting"] = False
            if not listen_state["active"]:
                return False
            try:
                ctrl.start_live_listen(_on_listen_update, prefer=_prefer_mode())
            except Exception as exc:  # noqa: BLE001
                _set_listening_ui(False)
                _error(window, "Could not restart key listen", str(exc))
            return False

        GLib.timeout_add(400, restart)

    def _on_daemon_toggled(_switch: Any, _pspec: Any = None) -> None:
        if listen_state["suppress_daemon"] or listen_state["daemon_busy"]:
            _sync_daemon_row()
            return
        want_on = daemon_switch.get_active()
        _sync_daemon_row()
        listen_state["daemon_busy"] = True
        daemon_switch.set_sensitive(False)
        live_status.set_subtitle(
            "Starting remap daemon…" if want_on else "Stopping remap daemon…"
        )

        def work() -> Any:
            if want_on:
                return daemon_ctrl.start_daemon()
            return daemon_ctrl.stop_daemon()

        def done(result: Any, error: BaseException | None) -> None:
            listen_state["daemon_busy"] = False
            daemon_switch.set_sensitive(True)
            if error:
                _sync_daemon_row(from_status=True)
                _error(window, "Daemon toggle failed", str(error))
                return
            running = bool(getattr(result, "running", want_on))
            listen_state["suppress_daemon"] = True
            try:
                daemon_switch.set_active(running)
            finally:
                listen_state["suppress_daemon"] = False
            _sync_daemon_row()
            _refresh_header_daemon(window)
            detail = getattr(result, "detail", "") or ""
            if running != want_on:
                _error(
                    window,
                    "Daemon toggle failed",
                    detail or ("still running" if running else "not running"),
                )
            else:
                _toast(
                    window,
                    f"Daemon {'started' if running else 'stopped'}"
                    + (f" ({detail})" if detail else ""),
                )
            if listen_state["active"]:
                _restart_listen_if_active()
            elif not listen_state["active"]:
                live_status.set_subtitle("Idle")

        run_in_thread(work, done)

    def _start_listen(_b: Any = None) -> None:
        _begin_listen()

    def _stop_listen(_b: Any = None) -> None:
        _finish_listen()

    def _reload_profile(_b: Any = None) -> None:
        try:
            ctrl.reload_live_listen_profile()
            _toast(window, "Profile mapping refreshed")
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not reload profile", str(exc))

    _sync_daemon_row(from_status=True)
    live.add(daemon_row)
    live.add(live_status)
    for title, btn in (
        ("Start listening", start_btn),
        ("Stop", stop_btn),
        ("Reload profile map", reload_btn),
    ):
        row = Adw.ActionRow(title=title)
        row.add_suffix(btn)
        live.add(row)
    daemon_switch.connect("notify::active", _on_daemon_toggled)
    start_btn.connect("clicked", _start_listen)
    stop_btn.connect("clicked", _stop_listen)
    reload_btn.connect("clicked", _reload_profile)

    page.add(live)

    group = Adw.PreferencesGroup(
        title="Remote debug dump",
        description="CLI: tartarus-v2 diagnose — paste between COPY banners",
    )

    skip = Gtk.Switch()
    skip_row = Adw.ActionRow(title="Skip USB probe")
    skip_row.add_suffix(skip)
    skip_row.set_activatable_widget(skip)

    listen = Gtk.SpinButton.new_with_range(0, 30, 1)
    listen_row = Adw.ActionRow(title="Listen seconds (dump only)")
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
        try:
            saved = ctrl.save_report(out_entry.get_text().strip() or "~/tartarus-diagnose.log")
            _toast(window, f"Saved {saved}")
        except Exception as exc:  # noqa: BLE001
            _error(window, "Could not save report", str(exc))

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
        labels = {
            "Run diagnose": "Run",
            "Copy report": "Copy",
            "Save report": "Save",
            "Open preview": "Open",
        }
        b = Gtk.Button(label=labels.get(title, "Run"))
        if suggested:
            b.add_css_class("suggested-action")
        b.connect("clicked", cb)
        row.add_suffix(b)
        group.add(row)

    page.add(group)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    content.append(page)
    content.append(pressed_box)
    content.append(log_box)
    scroll.set_child(content)
    outer.append(scroll)

    def _on_page_map(_w: Any) -> None:
        if not listen_state["daemon_busy"]:
            _sync_daemon_row(from_status=True)

    outer.connect("map", _on_page_map)

    def _cleanup(*_args: Any) -> None:
        if listen_state["active"]:
            _finish_listen()

    try:
        window.connect("close-request", lambda *_: (_cleanup(), False)[1])
    except Exception:  # noqa: BLE001
        pass

    return outer
