"""App-menu and tray 'Check for updates' dialogs."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("tartarus_v2.gui.update")


def present_update_check(window: Any) -> None:
    """Query GitHub on a worker thread, then offer to install a newer .deb."""
    from gi.repository import Adw

    from tartarus_v2.gui.workers import run_in_thread

    def work() -> Any:
        from tartarus_v2 import actions

        return actions.check_for_update()

    def done(result: Any, error: BaseException | None) -> None:
        if error is not None or result is None:
            _alert(window, "Could not check for updates", str(error or "unknown error"))
            return
        if not result.update_available:
            _alert(window, "Tartarus V2", result.detail)
            return
        if not result.asset_url:
            _alert(window, f"Update {result.latest}", result.detail)
            return
        dialog = Adw.AlertDialog.new(
            f"Update to {result.latest}?",
            f"{result.detail} This downloads the release and installs it "
            "(admin approval). Restart Tartarus V2 afterward. "
            "The remap daemon does not need to run as root.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install update")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("install")
        dialog.set_close_response("cancel")

        def on_response(_d: Any, response: str) -> None:
            if response != "install":
                return
            _toast(window, f"Installing {result.latest}…")

            def install() -> str:
                from tartarus_v2 import actions

                return actions.install_update(result)

            def installed(message: Any, install_error: BaseException | None) -> None:
                if install_error is not None:
                    _alert(window, "Update failed", str(install_error))
                    return
                text = str(message or "")
                if text.startswith("Installed"):
                    _alert(window, "Update installed", text)
                else:
                    _alert(window, "Update failed", text)

            run_in_thread(install, installed)

        dialog.connect("response", on_response)
        dialog.present(window)

    run_in_thread(work, done)


def _alert(window: Any, title: str, body: str) -> None:
    from gi.repository import Adw

    dialog = Adw.AlertDialog.new(title, body)
    dialog.add_response("ok", "OK")
    dialog.set_default_response("ok")
    dialog.set_close_response("ok")
    dialog.present(window)


def _toast(window: Any, text: str) -> None:
    try:
        from gi.repository import Adw

        overlay = getattr(window, "_toast_overlay", None)
        if overlay is not None:
            overlay.add_toast(Adw.Toast.new(text))
    except Exception:  # noqa: BLE001
        log.info("%s", text)
