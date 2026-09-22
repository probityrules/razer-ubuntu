"""Clickable Tartarus V2 keymap widget (GTK4)."""

from __future__ import annotations

from typing import Any, Callable

from tartarus_v2.input.keys import KEYMAP_LAYOUT, short_label


def _format_binding(value: Any) -> str:
    if value is None:
        return "(unset)"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        kind = value.get("type", "action")
        if kind == "macro":
            return "macro"
        return str(kind)
    return str(value)


def build_keymap_grid(
    on_select: Callable[[str], None],
    *,
    selected: str | None = None,
    layer_label: str = "Normal",
    bindings: dict[str, Any] | None = None,
) -> Any:
    """Return a Gtk.Box with a labeled grid; clicking a key calls on_select(logical)."""
    from gi.repository import Gtk

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.set_margin_start(12)
    outer.set_margin_end(12)
    outer.set_margin_top(8)
    outer.set_margin_bottom(8)

    title = Gtk.Label(label=f"Device layout — {layer_label}")
    title.add_css_class("heading")
    title.set_xalign(0)
    outer.append(title)

    hint = Gtk.Label(
        label="Click a key to select it. Toggle Normal / Hypershift above to edit each layer."
    )
    hint.add_css_class("dim-label")
    hint.set_wrap(True)
    hint.set_xalign(0)
    outer.append(hint)

    grid = Gtk.Grid(column_spacing=6, row_spacing=6)
    grid.set_halign(Gtk.Align.CENTER)
    buttons: dict[str, Any] = {}
    current_bindings: dict[str, Any] = dict(bindings or {})

    def _style_selected() -> None:
        for name, btn in buttons.items():
            if selected is not None and name == selected:
                btn.add_css_class("suggested-action")
            else:
                btn.remove_css_class("suggested-action")

    def _refresh_tooltips() -> None:
        for name, btn in buttons.items():
            tip = name
            if name in current_bindings:
                tip = f"{name} → {_format_binding(current_bindings[name])}"
            btn.set_tooltip_text(tip)

    for r, row in enumerate(KEYMAP_LAYOUT):
        for c, logical in enumerate(row):
            if logical is None:
                spacer = Gtk.Label(label="")
                spacer.set_size_request(48, 36)
                grid.attach(spacer, c, r, 1, 1)
                continue

            btn = Gtk.Button(label=short_label(logical))
            btn.set_size_request(56, 40)
            btn.add_css_class("flat")
            btn.add_css_class("keymap-key")

            def _clicked(_button: Any, name: str = logical) -> None:
                nonlocal selected
                selected = name
                _style_selected()
                on_select(name)

            btn.connect("clicked", _clicked)
            buttons[logical] = btn
            grid.attach(btn, c, r, 1, 1)

    _style_selected()
    _refresh_tooltips()
    outer.append(grid)

    def set_selected(name: str) -> None:
        nonlocal selected
        selected = name
        _style_selected()

    def set_layer_label(label: str) -> None:
        title.set_label(f"Device layout — {label}")

    def set_bindings(new_bindings: dict[str, Any] | None) -> None:
        nonlocal current_bindings
        current_bindings = dict(new_bindings or {})
        _refresh_tooltips()

    outer._keymap_buttons = buttons  # noqa: SLF001
    outer._keymap_set_selected = set_selected  # noqa: SLF001
    outer._keymap_set_layer_label = set_layer_label  # noqa: SLF001
    outer._keymap_set_bindings = set_bindings  # noqa: SLF001
    return outer
