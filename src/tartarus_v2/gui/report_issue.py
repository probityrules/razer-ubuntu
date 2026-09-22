"""Report issue dialog (Notefully-style note + diagnostics, no screenshots)."""

from __future__ import annotations

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


def show_report_issue_dialog(window: Any) -> None:
    from gi.repository import Adw, Gtk

    cfg = load_config()
    dialog = Adw.Dialog()
    dialog.set_title("Report issue")
    dialog.set_content_width(520)
    dialog.set_content_height(560)

    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_show_end_title_buttons(True)
    toolbar.add_top_bar(header)

    page = Adw.PreferencesPage()
    group = Adw.PreferencesGroup(
        title="Feedback",
        description=(
            "Sent to Notefully with a fresh diagnose dump and recent logs. "
            "Your reporter name is remembered for next time."
        ),
    )

    kind_row = Adw.ActionRow(title="Kind")
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
        label = kind_id.capitalize()
        btn = Gtk.ToggleButton(label=label)
        if kind_id == "bug":
            btn.set_active(True)
        btn.connect("toggled", on_kind_toggled, kind_id)
        kind_buttons[kind_id] = btn
        kind_box.append(btn)

    kind_row.add_suffix(kind_box)
    group.add(kind_row)

    author_row = Adw.EntryRow(title="Reporter")
    author_row.set_tooltip_text("Remembered on this machine and autofilled next time.")
    author_row.set_text(load_author())
    group.add(author_row)
    page.add(group)

    note_group = Adw.PreferencesGroup(title="Note")
    note_row = Adw.ActionRow()
    note_row.set_activatable(False)
    note_scroll = Gtk.ScrolledWindow()
    note_scroll.set_min_content_height(140)
    note_scroll.set_hexpand(True)
    note_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    note_view = Gtk.TextView()
    note_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    note_view.set_top_margin(8)
    note_view.set_bottom_margin(8)
    note_view.set_left_margin(8)
    note_view.set_right_margin(8)
    note_view.set_hexpand(True)
    note_buffer = note_view.get_buffer()
    note_scroll.set_child(note_view)
    # Prefer child over suffix so the editor gets full width.
    try:
        note_row.set_child(note_scroll)
    except (AttributeError, TypeError):
        note_row.add_suffix(note_scroll)
    note_group.add(note_row)
    page.add(note_group)

    attach = Adw.PreferencesGroup(
        title="Attachments",
        description=(
            "Each submit regenerates a fresh diagnose dump (USB/HID/permissions/log tail) "
            "and attaches recent console lines. No screenshots."
        ),
    )
    page.add(attach)

    key_row: Adw.EntryRow | None = None
    if not cfg.project_key:
        setup = Adw.PreferencesGroup(
            title="Notefully setup",
            description=(
                "Paste your public project key (nfk_…) from Showfully → Notefully → Settings. "
                "It is saved under ~/.config/tartarus-v2/."
            ),
        )
        key_row = Adw.EntryRow(title="Project key")
        setup.add(key_row)
        page.add(setup)

    status = Gtk.Label(label="", xalign=0.0, wrap=True)
    status.add_css_class("dim-label")
    status.set_margin_start(12)
    status.set_margin_end(12)
    status.set_margin_top(4)
    status.set_margin_bottom(4)

    # Bottom action bar — always visible (header pack_* is easy to miss / clip in Adw.Dialog).
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    actions.set_margin_top(8)
    actions.set_margin_bottom(12)
    actions.set_margin_start(12)
    actions.set_margin_end(12)
    cancel_btn = Gtk.Button(label="Cancel")
    submit_btn = Gtk.Button(label="Submit")
    submit_btn.add_css_class("suggested-action")
    submit_btn.set_can_default(True)
    actions.append(cancel_btn)
    actions.append(submit_btn)

    footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    footer.append(status)
    footer.append(actions)
    toolbar.add_bottom_bar(footer)

    scroll = Gtk.ScrolledWindow(child=page)
    scroll.set_vexpand(True)
    toolbar.set_content(scroll)
    dialog.set_child(toolbar)

    def set_busy(busy: bool) -> None:
        submit_btn.set_sensitive(not busy)
        cancel_btn.set_sensitive(not busy)
        note_view.set_sensitive(not busy)
        author_row.set_sensitive(not busy)
        if key_row is not None:
            key_row.set_sensitive(not busy)
        for btn in kind_buttons.values():
            btn.set_sensitive(not busy)
        if busy:
            submit_btn.set_label("Submitting…")
        else:
            submit_btn.set_label("Submit")

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
        if key_row is not None:
            project_key = key_row.get_text().strip()
            if not project_key:
                status.set_label("Enter your Notefully project key (nfk_…).")
                return
            save_project_key(project_key)

        author = author_row.get_text().strip()
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
    dialog.present(window)
