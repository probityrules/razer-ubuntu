"""Feature parity: every CLI command must map to actions + GUI handlers."""

from __future__ import annotations

from tartarus_v2 import actions
from tartarus_v2.cli import build_parser
from tartarus_v2.features import FEATURE_MAP, GUI_EXTRA_HANDLERS, cli_ids, collect_argparse_commands
from tartarus_v2.gui.controllers import PAGE_CONTROLLERS, get_handler
from tartarus_v2.gui.tray import TrayController, menu_action_ids


def test_argparse_commands_match_feature_map() -> None:
    parser = build_parser()
    from_parser = collect_argparse_commands(parser)
    from_map = cli_ids()
    assert from_parser == from_map, (
        f"CLI/map mismatch missing_in_map={from_parser - from_map} "
        f"extra_in_map={from_map - from_parser}"
    )


def test_every_feature_has_action() -> None:
    for feature in FEATURE_MAP:
        assert hasattr(actions, feature.action), f"missing action {feature.action}"
        assert callable(getattr(actions, feature.action))


def test_every_feature_has_gui_handler() -> None:
    for feature in FEATURE_MAP:
        get_handler(feature.gui_page, feature.gui_handler)


def test_gui_extra_handlers_exist() -> None:
    for page, handler in GUI_EXTRA_HANDLERS:
        get_handler(page, handler)


def test_page_controllers_cover_map_pages() -> None:
    pages = {f.gui_page for f in FEATURE_MAP}
    assert pages <= set(PAGE_CONTROLLERS)


def test_tray_menu_actions() -> None:
    ids = menu_action_ids()
    ctrl = TrayController()
    for name in ids:
        assert hasattr(ctrl, name), name


def test_tray_status_text() -> None:
    from tartarus_v2.gui.tray import tray_status_text

    label, tip = tray_status_text(profile="default", daemon_running=True)
    assert label == "default"
    assert "default" in tip and "ON" in tip

    label_off, tip_off = tray_status_text(profile="arena", daemon_running=False)
    assert label_off == "arena"
    assert "OFF" in tip_off

    long_name = "a" * 20
    short, _ = tray_status_text(profile=long_name, daemon_running=True)
    assert short.endswith("…")
    assert len(short) == 16
