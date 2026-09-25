"""Clickable Tartarus V2 keymap widget (GTK4) with N/HS labels and press highlight."""

from __future__ import annotations

from typing import Any, Callable

from tartarus_v2.input.keys import KEYMAP_LAYOUT, describe_logical, short_label

_UNSET = object()
_CSS_LOADED = False

_KEYMAP_CSS = b"""
button.keymap-key {
  min-width: 88px;
  min-height: 72px;
  padding: 6px 8px;
  border-radius: 8px;
}
button.keymap-key label.keymap-name {
  font-weight: 700;
  font-size: 0.95em;
}
button.keymap-key label.keymap-n {
  color: #3584e4;
  font-size: 0.78em;
  font-weight: 600;
}
button.keymap-key label.keymap-h {
  color: #e66100;
  font-size: 0.78em;
  font-weight: 600;
}
button.keymap-key label.keymap-hs {
  color: #9a9996;
  font-size: 0.85em;
  font-weight: 700;
}
button.keymap-key:disabled {
  opacity: 0.55;
}
"""


def _ensure_keymap_css() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    from gi.repository import Gdk, Gtk

    provider = Gtk.CssProvider()
    provider.load_from_data(_KEYMAP_CSS)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
    _CSS_LOADED = True


def _format_binding(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value or "—"
    if isinstance(value, dict):
        kind = value.get("type", "action")
        if kind == "macro":
            steps = value.get("steps") or []
            if steps and isinstance(steps[0], dict) and steps[0].get("tap"):
                return f"m:{steps[0]['tap']}"
            return "macro"
        if kind == "key":
            return str(value.get("key") or value.get("keys") or "key")
        if kind == "profile_next":
            return "next"
        if kind == "profile_prev":
            return "prev"
        return str(kind)
    return str(value)


def build_keymap_grid(
    on_select: Callable[[str], None],
    *,
    selected: str | None = None,
    standard_bindings: dict[str, Any] | None = None,
    hypershift_bindings: dict[str, Any] | None = None,
    hypershift_key: str | None = None,
) -> Any:
    """Return a Gtk.Box grid; each cell shows id + Normal/Hypershift bindings."""
    from gi.repository import Gtk, Pango

    _ensure_keymap_css()

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.set_margin_start(12)
    outer.set_margin_end(12)
    outer.set_margin_top(8)
    outer.set_margin_bottom(8)

    title = Gtk.Label(label="Device layout")
    title.add_css_class("heading")
    title.set_xalign(0)
    outer.append(title)

    hint = Gtk.Label(
        label="Click a key to edit. N = Normal (blue), H = Hypershift (orange). HS key is reserved."
    )
    hint.add_css_class("dim-label")
    hint.set_wrap(True)
    hint.set_xalign(0)
    outer.append(hint)

    grid = Gtk.Grid(column_spacing=8, row_spacing=8)
    grid.set_halign(Gtk.Align.CENTER)

    cells: dict[str, dict[str, Any]] = {}
    std = dict(standard_bindings or {})
    hs = dict(hypershift_bindings or {})
    pressed: set[str] = set()
    selected_name = selected
    hs_key = hypershift_key

    def _is_hs(logical: str) -> bool:
        return bool(hs_key) and logical == hs_key

    def _style_cell(logical: str) -> None:
        info = cells.get(logical)
        if info is None:
            return
        btn = info["button"]
        btn.remove_css_class("suggested-action")
        btn.remove_css_class("destructive-action")
        reserved = _is_hs(logical)
        btn.set_sensitive(not reserved)
        if reserved:
            return
        if logical in pressed:
            btn.add_css_class("destructive-action")
        elif selected_name is not None and logical == selected_name:
            btn.add_css_class("suggested-action")

    def _refresh_cell(logical: str) -> None:
        info = cells.get(logical)
        if info is None:
            return
        info["name"].set_label(short_label(logical))
        if _is_hs(logical):
            info["n"].set_visible(False)
            info["h"].set_visible(False)
            info["reserved"].set_visible(True)
            tip = f"{describe_logical(logical)}\nReserved as Hypershift modifier"
        else:
            info["reserved"].set_visible(False)
            info["n"].set_visible(True)
            info["h"].set_visible(True)
            info["n"].set_label(f"N:{_format_binding(std.get(logical))}")
            info["h"].set_label(f"H:{_format_binding(hs.get(logical))}")
            tip = (
                f"{describe_logical(logical)}\n"
                f"Normal → {_format_binding(std.get(logical))}\n"
                f"Hypershift → {_format_binding(hs.get(logical))}"
            )
        info["button"].set_tooltip_text(tip)
        _style_cell(logical)

    def _refresh_all() -> None:
        for logical in cells:
            _refresh_cell(logical)

    for r, row in enumerate(KEYMAP_LAYOUT):
        for c, logical in enumerate(row):
            if logical is None:
                spacer = Gtk.Label(label="")
                spacer.set_size_request(72, 52)
                grid.attach(spacer, c, r, 1, 1)
                continue

            btn = Gtk.Button()
            btn.set_size_request(88, 72)
            btn.add_css_class("keymap-key")

            stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            stack.set_halign(Gtk.Align.CENTER)
            stack.set_valign(Gtk.Align.CENTER)

            name_lbl = Gtk.Label(label=short_label(logical))
            name_lbl.add_css_class("keymap-name")
            name_lbl.set_halign(Gtk.Align.CENTER)

            n_lbl = Gtk.Label(label="N:—")
            n_lbl.add_css_class("keymap-n")
            n_lbl.set_halign(Gtk.Align.CENTER)
            n_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            n_lbl.set_max_width_chars(10)

            h_lbl = Gtk.Label(label="H:—")
            h_lbl.add_css_class("keymap-h")
            h_lbl.set_halign(Gtk.Align.CENTER)
            h_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            h_lbl.set_max_width_chars(10)

            reserved_lbl = Gtk.Label(label="HS")
            reserved_lbl.add_css_class("keymap-hs")
            reserved_lbl.set_halign(Gtk.Align.CENTER)
            reserved_lbl.set_visible(False)

            stack.append(name_lbl)
            stack.append(n_lbl)
            stack.append(h_lbl)
            stack.append(reserved_lbl)
            btn.set_child(stack)

            def _clicked(_button: Any, name: str = logical) -> None:
                nonlocal selected_name
                if _is_hs(name):
                    return
                selected_name = name
                _refresh_all()
                on_select(name)

            btn.connect("clicked", _clicked)
            cells[logical] = {
                "button": btn,
                "name": name_lbl,
                "n": n_lbl,
                "h": h_lbl,
                "reserved": reserved_lbl,
            }
            grid.attach(btn, c, r, 1, 1)

    _refresh_all()
    outer.append(grid)

    def set_selected(name: str | None) -> None:
        nonlocal selected_name
        if name is not None and _is_hs(name):
            selected_name = None
        else:
            selected_name = name
        _refresh_all()

    def set_bindings(
        *,
        standard: dict[str, Any] | None = None,
        hypershift: dict[str, Any] | None = None,
        hypershift_key: Any = _UNSET,
    ) -> None:
        nonlocal std, hs, hs_key, selected_name
        if standard is not None:
            std = dict(standard)
        if hypershift is not None:
            hs = dict(hypershift)
        if hypershift_key is not _UNSET:
            hs_key = hypershift_key or None
            if selected_name is not None and _is_hs(selected_name):
                selected_name = None
        _refresh_all()

    def set_pressed(logicals: set[str] | list[str]) -> None:
        nonlocal pressed
        pressed = set(logicals)
        _refresh_all()

    def set_hypershift_key(logical: str | None) -> None:
        set_bindings(hypershift_key=logical)

    outer._keymap_cells = cells  # noqa: SLF001
    outer._keymap_set_selected = set_selected  # noqa: SLF001
    outer._keymap_set_bindings = set_bindings  # noqa: SLF001
    outer._keymap_set_pressed = set_pressed  # noqa: SLF001
    outer._keymap_set_hypershift_key = set_hypershift_key  # noqa: SLF001
    # Back-compat no-ops for older callers
    outer._keymap_set_layer_label = lambda _label: None  # noqa: SLF001
    outer._keymap_buttons = {k: v["button"] for k, v in cells.items()}  # noqa: SLF001
    return outer
