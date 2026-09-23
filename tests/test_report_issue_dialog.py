"""Report issue dialog wiring + GTK smoke construction."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tartarus_v2.notefully import NotefullyConfig

ROOT = Path(__file__).resolve().parents[1]
GUI_SRC = ROOT / "src" / "tartarus_v2" / "gui"


def test_report_issue_menu_and_action_wired() -> None:
    """Catch an unhooked menu item or missing app action without needing GTK."""
    window_src = (GUI_SRC / "window.py").read_text(encoding="utf-8")
    app_src = (GUI_SRC / "app.py").read_text(encoding="utf-8")
    assert 'menu.append("Report issue' in window_src
    assert '"app.report_issue"' in window_src
    assert 'SimpleAction.new("report_issue"' in app_src
    assert "show_report_issue_dialog" in app_src


def _gtk_ready() -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("Report dialog smoke test requires Linux + GTK")
    from tartarus_v2.gui.gi_check import GuiUnavailable, require_gi

    try:
        require_gi()
    except GuiUnavailable as exc:
        pytest.skip(str(exc))

    from gi.repository import Adw, Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("GTK display not available (headless without xvfb)")
    Adw.init()


def _iter_widgets(root: object) -> list[object]:
    """Depth-first walk of GTK4 / Adw widget tree."""
    out: list[object] = []
    stack = [root]
    seen: set[int] = set()
    while stack:
        widget = stack.pop()
        wid = id(widget)
        if wid in seen:
            continue
        seen.add(wid)
        out.append(widget)
        get_child = getattr(widget, "get_child", None)
        if callable(get_child):
            try:
                child = get_child()
            except TypeError:
                child = None
            if child is not None:
                stack.append(child)
        get_content = getattr(widget, "get_content", None)
        if callable(get_content):
            try:
                content = get_content()
            except TypeError:
                content = None
            if content is not None:
                stack.append(content)
        get_first = getattr(widget, "get_first_child", None)
        if callable(get_first):
            child = get_first()
            while child is not None:
                stack.append(child)
                child = child.get_next_sibling()
    return out


def _button_labels(root: object) -> set[str]:
    from gi.repository import Gtk

    labels: set[str] = set()
    for widget in _iter_widgets(root):
        if isinstance(widget, Gtk.Button):
            label = widget.get_label()
            if label:
                labels.add(label)
    return labels


@pytest.mark.gui
@pytest.mark.parametrize("project_key", ["", "nfk_test_key"])
def test_report_issue_dialog_builds(project_key: str) -> None:
    """Construct the dialog; catches PreferenceGroup / set_child style open crashes."""
    _gtk_ready()

    cfg = NotefullyConfig(
        endpoint="https://example.test/notefully",
        project_key=project_key,
    )
    with (
        patch("tartarus_v2.gui.report_issue.load_config", return_value=cfg),
        patch("tartarus_v2.gui.report_issue.load_author", return_value="Tester"),
    ):
        from tartarus_v2.gui.report_issue import build_report_issue_dialog

        dialog = build_report_issue_dialog(MagicMock())

    assert dialog.get_title() == "Report issue"
    assert dialog.get_child() is not None
    labels = _button_labels(dialog)
    assert "Submit" in labels
    assert "Cancel" in labels
