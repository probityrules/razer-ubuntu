"""Macro playback helpers."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

log = logging.getLogger("tartarus_v2.macros")

EmitFn = Callable[[list[int], bool], None]


def play_macro(steps: list[dict[str, Any]], emit: EmitFn, resolve_keys: Callable[[Any], list[int]]) -> None:
    """
    steps examples:
      {"press": "KEY_A"}
      {"release": "KEY_A"}
      {"tap": ["KEY_LEFTCTRL", "KEY_C"]}
      {"delay_ms": 50}
    """
    for step in steps:
        if "delay_ms" in step:
            time.sleep(max(0, int(step["delay_ms"])) / 1000.0)
            continue
        if "tap" in step:
            codes = resolve_keys(step["tap"])
            emit(codes, True)
            time.sleep(0.02)
            emit(list(reversed(codes)), False)
            continue
        if "press" in step:
            emit(resolve_keys(step["press"]), True)
            continue
        if "release" in step:
            emit(resolve_keys(step["release"]), False)
            continue
        log.warning("Unknown macro step: %r", step)
