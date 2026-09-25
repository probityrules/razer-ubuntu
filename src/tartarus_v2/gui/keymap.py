"""Clickable Tartarus V2 keymap widget (GTK4) with N/HS labels and press highlight."""

from __future__ import annotations

from typing import Any, Callable

from tartarus_v2.input.keys import KEYMAP_LAYOUT, describe_logical, short_label

_UNSET = object()


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
    from gi.repository import Gtk

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
        label="Click a key to edit. N = Normal, H = Hypershift. HS key is reserved."
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

    def _cell_label(logical: str) -> str:
        if _is_hs(logical):
            return f"{short_label(logical)}\nHS"
        n = _format_binding(std.get(logical))
        h = _format_binding(hs.get(logical))
        return f"{short_label(logical)}\nN:{n}\nH:{h}"

    def _style_cell(logical: str) -> None:
        info = cells.get(logical)
        if info is None:
            return
        btn = info["button"]
        btn.remove_css_class("suggested-action")
        btn.remove_css_class("destructive-action")
        btn.remove_css_class("opaque")
        reserved = _is_hs(logical)
        btn.set_sensitive(not reserved)
        if reserved:
            return
        if logical in pressed:
            btn.add_css_class("destructive-action")
        elif selected_name is not None and logical == selected_name:
            btn.add_css_class("suggested-action")

    def _refresh_all() -> None:
        for logical, info in cells.items():
            info["button"].set_label(_cell_label(logical))
            if _is_hs(logical):
                tip = f"{describe_logical(logical)}\nReserved as Hypershift modifier"
            else:
                tip = (
                    f"{describe_logical(logical)}\n"
                    f"Normal → {_format_binding(std.get(logical))}\n"
                    f"Hypershift → {_format_binding(hs.get(logical))}"
                )
            info["button"].set_tooltip_text(tip)
            _style_cell(logical)

    for r, row in enumerate(KEYMAP_LAYOUT):
        for c, logical in enumerate(row):
            if logical is None:
                spacer = Gtk.Label(label="")
                spacer.set_size_request(72, 52)
                grid.attach(spacer, c, r, 1, 1)
                continue

            btn = Gtk.Button(label=_cell_label(logical))
            btn.set_size_request(88, 64)
            btn.add_css_class("flat")
            btn.add_css_class("keymap-key")

            def _clicked(_button: Any, name: str = logical) -> None:
                nonlocal selected_name
                if _is_hs(name):
                    return
                selected_name = name
                _refresh_all()
                on_select(name)

            btn.connect("clicked", _clicked)
            cells[logical] = {"button": btn}
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
