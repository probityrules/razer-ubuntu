"""Background helpers for GTK UI (safe to import without GI)."""

from __future__ import annotations

import threading
from typing import Any, Callable


def run_in_thread(work: Callable[[], Any], on_done: Callable[[Any, BaseException | None], None]) -> None:
    """Run work off the main thread; call on_done(result, error) when finished.

    When GI is available, on_done is marshalled onto the GLib main loop.
    Otherwise on_done runs on the worker thread (unit tests).
    """

    def _finish(result: Any, error: BaseException | None) -> None:
        try:
            import gi  # noqa: F401
            from gi.repository import GLib

            GLib.idle_add(lambda: (on_done(result, error), False)[1])
        except Exception:  # noqa: BLE001
            on_done(result, error)

    def _target() -> None:
        try:
            result = work()
        except BaseException as exc:  # noqa: BLE001
            _finish(None, exc)
            return
        _finish(result, None)

    threading.Thread(target=_target, daemon=True).start()
