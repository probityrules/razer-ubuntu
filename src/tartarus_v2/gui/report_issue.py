"""Report issue dialog (Notefully-style note + diagnostics, no screenshots)."""

from __future__ import annotations

import logging
from typing import Any

from tartarus_v2.gui.workers import run_in_thread
from tartarus_v2.notefully import (
    KINDS,
    NotefullyConfig,
    load_author,
    load_config,
    save_author,
    save_project_key,
    submit_report,
)

log = logging.getLogger("tartarus_v2.gui.report_issue")


def show_report_issue_dialog(window: Any) -> None:
    """Open the Report issue dialog. Errors are toasted instead of failing silently."""
    try:
        _build_and_present(window)
    except Exception as exc:  # noqa: BLE001
        log.exception("Report issue dialog failed to open")
        try:
            from gi.repository import Adw

            overlay = getattr(window, "_toast_overlay", None)
            if overlay is not None:
                overlay.add_toast(Adw.Toast.new(f"Report issue failed: {exc}"))
            else:
                dialog = Adw.AlertDialog.new("Report issue failed", str(exc))
                dialog.add_response("ok", "OK")
                dialog.present(window)
        except Exception:  # noqa: BLE001
            pass


def _build_and_present(window: Any) -> None:
    dialog = build_report_issue_dialog(window)
    dialog.present(window)


def build_report_issue_dialog(window: Any) -> Any:
    """Build the Report issue dialog (no present). Used by GUI and smoke tests."""
    from gi.repository import Adw, Gtk

    cfg = load_config()
    dialog = Adw.Dialog()
    dialog.set_title("Report issue")
    try:
        dialog.set_content_width(520)
        dialog.set_content_height(560)
    except AttributeError:
        pass

    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    try:
        header.set_show_end_title_buttons(True)
    except AttributeError:
        pass
    toolbar.add_top_bar(header)

    # Vertical content (avoid empty PreferencesGroups / ActionRow.set_child quirks).
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    body.set_margin_start(16)
    body.set_margin_end(16)
    body.set_margin_top(12)
    body.set_margin_bottom(8)

    intro = Gtk.Label(
        label=(
            "Sent to Notefully with a fresh diagnose dump and recent logs. "
            "Your reporter name is remembered for next time."
        ),
        wrap=True,
        xalign=0.0,
    )
    intro.add_css_class("dim-label")
    body.append(intro)

    kind_label = Gtk.Label(label="Kind", xalign=0.0)
    kind_label.add_css_class("heading")
    body.append(kind_label)

    kind_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    kind_box.add_css_class("linked")
    kind_state = {"kind": "bug"}
    kind_buttons: dict[str, Gtk.ToggleButton] = {}

    def on_kind_toggled(btn: Gtk.ToggleButton, kind_id: str) -> None:
        if not btn.get_active():
            return
        kind_state["kind"] = kind_id
        for kid, other in kind_buttons.items():
            if kid != kind_id and other.get_active():
                other.set_active(False)

    for kind_id in KINDS:
        btn = Gtk.ToggleButton(label=kind_id.capitalize())
        if kind_id == "bug":
            btn.set_active(True)
        btn.connect("toggled", on_kind_toggled, kind_id)
        kind_buttons[kind_id] = btn
        kind_box.append(btn)
    body.append(kind_box)

    author_label = Gtk.Label(label="Reporter", xalign=0.0)
    author_label.add_css_class("heading")
    body.append(author_label)
    author_entry = Gtk.Entry()
    author_entry.set_placeholder_text("Your name")
    author_entry.set_text(load_author())
    author_entry.set_tooltip_text("Remembered on this machine and autofilled next time.")
    body.append(author_entry)

    note_label = Gtk.Label(label="Note", xalign=0.0)
    note_label.add_css_class("heading")
    body.append(note_label)
    note_scroll = Gtk.ScrolledWindow()
    note_scroll.set_min_content_height(140)
    note_scroll.set_vexpand(True)
    note_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    note_frame = Gtk.Frame()
    note_view = Gtk.TextView()
    note_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    note_view.set_top_margin(8)
    note_view.set_bottom_margin(8)
    note_view.set_left_margin(8)
    note_view.set_right_margin(8)
    note_buffer = note_view.get_buffer()
    note_scroll.set_child(note_view)
    note_frame.set_child(note_scroll)
    body.append(note_frame)

    attach_hint = Gtk.Label(
        label=(
            "On submit: fresh diagnose dump (USB/HID/permissions/log) "
            "+ recent console lines. No screenshots."
        ),
        wrap=True,
        xalign=0.0,
    )
    attach_hint.add_css_class("dim-label")
    body.append(attach_hint)

    key_entry: Gtk.Entry | None = None
    if not cfg.project_key:
        key_label = Gtk.Label(label="Notefully project key", xalign=0.0)
        key_label.add_css_class("heading")
        body.append(key_label)
        key_hint = Gtk.Label(
            label="Paste your public nfk_… key (saved under ~/.config/tartarus-v2/).",
            wrap=True,
            xalign=0.0,
        )
        key_hint.add_css_class("dim-label")
        body.append(key_hint)
        key_entry = Gtk.Entry()
        key_entry.set_placeholder_text("nfk_…")
        body.append(key_entry)

    status = Gtk.Label(label="", xalign=0.0, wrap=True)
    status.add_css_class("dim-label")
    body.append(status)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    actions.set_margin_top(4)
    cancel_btn = Gtk.Button(label="Cancel")
    submit_btn = Gtk.Button(label="Submit")
    submit_btn.add_css_class("suggested-action")
    actions.append(cancel_btn)
    actions.append(submit_btn)
    body.append(actions)

    scroll = Gtk.ScrolledWindow()
    scroll.set_child(body)
    scroll.set_vexpand(True)
    toolbar.set_content(scroll)
    dialog.set_child(toolbar)

    def set_busy(busy: bool) -> None:
        submit_btn.set_sensitive(not busy)
        cancel_btn.set_sensitive(not busy)
        note_view.set_sensitive(not busy)
        author_entry.set_sensitive(not busy)
        if key_entry is not None:
            key_entry.set_sensitive(not busy)
        for btn in kind_buttons.values():
            btn.set_sensitive(not busy)
        submit_btn.set_label("Submitting…" if busy else "Submit")

    def on_cancel(_b: Any = None) -> None:
        dialog.close()

    def on_submit(_b: Any = None) -> None:
        start = note_buffer.get_start_iter()
        end = note_buffer.get_end_iter()
        message = note_buffer.get_text(start, end, False).strip()
        if not message:
            status.set_label("Add a note before submitting.")
            return

        project_key = cfg.project_key
        if key_entry is not None:
            project_key = key_entry.get_text().strip()
            if not project_key:
                status.set_label("Enter your Notefully project key (nfk_…).")
                return
            save_project_key(project_key)

        author = author_entry.get_text().strip()
        if author:
            save_author(author)
        kind = kind_state["kind"]
        submit_cfg = NotefullyConfig(endpoint=cfg.endpoint, project_key=project_key)

        set_busy(True)
        status.set_label("Gathering a fresh diagnose dump and submitting…")

        def work() -> Any:
            return submit_report(
                message=message,
                kind=kind,
                author=author,
                config=submit_cfg,
            )

        def done(result: Any, error: BaseException | None) -> None:
            set_busy(False)
            if error is not None:
                status.set_label(str(error))
                return
            if result is None or not getattr(result, "ok", False):
                status.set_label(getattr(result, "error", None) or "Submit failed.")
                return
            rid = getattr(result, "report_id", "") or ""
            toast_msg = f"Report sent{f' ({rid})' if rid else ''}."
            overlay = getattr(window, "_toast_overlay", None)
            if overlay is not None:
                overlay.add_toast(Adw.Toast.new(toast_msg))
            dialog.close()

        run_in_thread(work, done)

    cancel_btn.connect("clicked", on_cancel)
    submit_btn.connect("clicked", on_submit)
    return dialog
