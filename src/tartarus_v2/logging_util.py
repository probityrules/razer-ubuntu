"""Logging helpers for daemon and diagnose."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from tartarus_v2.constants import CACHE_DIR_NAME, LOG_FILE_NAME


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        path = Path(base) / CACHE_DIR_NAME
    else:
        path = Path.home() / ".cache" / CACHE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return cache_dir() / LOG_FILE_NAME


def setup_logging(debug: bool = False, also_stderr: bool = True) -> logging.Logger:
    logger = logging.getLogger("tartarus_v2")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    fh = logging.FileHandler(log_path(), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if also_stderr:
        sh = logging.StreamHandler()
        sh.setLevel(logging.DEBUG if debug else logging.INFO)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    return logger


def hex_dump(data: bytes | bytearray, width: int = 16) -> str:
    lines: list[str] = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:04x}: {hex_part:<{width * 3}}  |{ascii_part}|")
    return "\n".join(lines)


def annotate_report(data: bytes | bytearray) -> str:
    """Human-readable annotation of a 90-byte Razer report."""
    if len(data) < 90:
        return f"(short report len={len(data)})\n{hex_dump(data)}"
    status = data[0]
    tx = data[1]
    remaining = int.from_bytes(data[2:4], "big")
    proto = data[4]
    data_size = data[5]
    cmd_class = data[6]
    cmd_id = data[7]
    args = data[8 : 8 + data_size]
    crc = data[88]
    reserved = data[89]
    return (
        f"status=0x{status:02x} tx=0x{tx:02x} remaining={remaining} proto=0x{proto:02x}\n"
        f"  data_size={data_size} class=0x{cmd_class:02x} cmd=0x{cmd_id:02x}\n"
        f"  args={args.hex(' ')}\n"
        f"  crc=0x{crc:02x} reserved=0x{reserved:02x}\n"
        f"{hex_dump(data)}"
    )
