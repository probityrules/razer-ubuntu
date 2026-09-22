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
    dialog.set_content_height(520)

    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    toolbar.add_top_bar(header)

    cancel_btn = Gtk.Button(label="Cancel")
    header.pack_start(cancel_btn)

    submit_btn = Gtk.Button(label="Submit")
    submit_btn.add_css_class("suggested-action")
    header.pack_end(submit_btn)

    page = Adw.PreferencesPage()
    group = Adw.PreferencesGroup(
        title="Feedback",
        description=(
            "Sent to Notefully with logs and a diagnose dump (no screenshots). "
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

    note_group = Adw.PreferencesGroup(title="Note")
    note_frame = Gtk.Frame()
    note_frame.set_margin_top(6)
    note_frame.set_margin_bottom(6)
    note_scroll = Gtk.ScrolledWindow()
    note_scroll.set_min_content_height(140)
    note_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    note_view = Gtk.TextView()
    note_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    note_view.set_top_margin(8)
    note_view.set_bottom_margin(8)
    note_view.set_left_margin(8)
    note_view.set_right_margin(8)
    note_buffer = note_view.get_buffer()
    note_scroll.set_child(note_view)
    note_frame.set_child(note_scroll)
    note_group.add(note_frame)

    opts = Adw.PreferencesGroup(title="Attachments")
    diag_row = Adw.SwitchRow(
        title="Include diagnostics",
        subtitle="Device/USB/permissions dump and recent daemon log",
    )
    diag_row.set_active(True)
    opts.add(diag_row)

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
    status.set_margin_bottom(8)

    page.add(group)
    page.add(note_group)
    page.add(opts)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    scroll = Gtk.ScrolledWindow(child=page)
    scroll.set_vexpand(True)
    content.append(scroll)
    content.append(status)
    toolbar.set_content(content)
    dialog.set_child(toolbar)

    def set_busy(busy: bool) -> None:
        submit_btn.set_sensitive(not busy)
        cancel_btn.set_sensitive(not busy)
        note_view.set_sensitive(not busy)
        author_row.set_sensitive(not busy)
        diag_row.set_sensitive(not busy)
        if key_row is not None:
            key_row.set_sensitive(not busy)
        for btn in kind_buttons.values():
            btn.set_sensitive(not busy)

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
        include_diag = bool(diag_row.get_active())
        kind = kind_state["kind"]
        submit_cfg = NotefullyConfig(endpoint=cfg.endpoint, project_key=project_key)

        set_busy(True)
        status.set_label("Gathering diagnostics and submitting…")

        def work() -> Any:
            return submit_report(
                message=message,
                kind=kind,
                author=author,
                include_diagnostics=include_diag,
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
