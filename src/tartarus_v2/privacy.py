"""Redact local identity from diagnose / Notefully reports.

Keeps hardware, permissions, and log *content* useful for support while
stripping username, hostname, and home-directory paths that are not needed
to debug remapping or lighting.
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

PLACEHOLDER_USER = "<user>"
PLACEHOLDER_HOST = "<host>"
PLACEHOLDER_HOME = "<home>"
PLACEHOLDER_SERIAL = "<serial>"

# Never treat these as a username to scrub (too short / collide with report text).
_SKIP_USERNAMES = frozenset(
    {
        "",
        "user",
        "root",
        "admin",
        "unknown",
        "nobody",
        "input",
        "plugdev",
        "home",
        "host",
    }
)


def _path_variants(path: str) -> list[str]:
    """Return path spellings that may appear in dumps (slash style, unresolved)."""
    raw = (path or "").strip()
    if not raw:
        return []
    variants = {raw}
    try:
        variants.add(str(Path(raw)))
        variants.add(os.path.normpath(raw))
    except Exception:  # noqa: BLE001
        pass
    # Cross-platform slash forms (logs often use / even on Windows).
    for item in list(variants):
        variants.add(item.replace("\\", "/"))
        variants.add(item.replace("/", "\\"))
    return [v for v in variants if len(v) >= 2]


def _identity_tokens() -> tuple[list[str], list[str], list[str]]:
    """Homes (longest first), usernames, hostnames to scrub."""
    homes: set[str] = set()
    users: set[str] = set()
    hosts: set[str] = set()

    try:
        home = str(Path.home())
        homes.update(_path_variants(home))
    except Exception:  # noqa: BLE001
        pass
    for key in ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        val = os.environ.get(key) or ""
        if val:
            homes.update(_path_variants(val))
            # Parent of XDG_* is often still identifying; prefer full env value only.

    try:
        from tartarus_v2.permissions import current_username

        users.add(current_username())
    except Exception:  # noqa: BLE001
        pass
    for key in ("USER", "USERNAME", "LOGNAME"):
        val = (os.environ.get(key) or "").strip()
        if val:
            users.add(val)

    try:
        node = (platform.node() or "").strip()
        if node:
            hosts.add(node)
            hosts.add(node.split(".")[0])  # short name if FQDN
    except Exception:  # noqa: BLE001
        pass
    for key in ("HOSTNAME", "COMPUTERNAME"):
        val = (os.environ.get(key) or "").strip()
        if val:
            hosts.add(val)
            hosts.add(val.split(".")[0])

    home_list = sorted({h for h in homes if h}, key=len, reverse=True)
    user_list = sorted(
        {u for u in users if u and u.lower() not in _SKIP_USERNAMES and len(u) >= 2},
        key=len,
        reverse=True,
    )
    host_list = sorted(
        {h for h in hosts if h and len(h) >= 2 and h.lower() not in {"localhost", "local"}},
        key=len,
        reverse=True,
    )
    return home_list, user_list, host_list


def _replace_token(text: str, token: str, placeholder: str) -> str:
    """Replace ``token`` when it appears as its own path/word segment."""
    if not token or token not in text:
        return text
    # Prefer whole-segment matches so short names do not corrupt hex/USB ids.
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_.-]){re.escape(token)}(?![A-Za-z0-9_.-])",
        re.IGNORECASE,
    )
    return pattern.sub(placeholder, text)


def redact_report_text(text: str) -> str:
    """Strip local username, hostname, and home paths from report text."""
    if not text:
        return text
    homes, users, hosts = _identity_tokens()
    out = text
    for home in homes:
        if home in out:
            out = out.replace(home, PLACEHOLDER_HOME)
    for host in hosts:
        out = _replace_token(out, host, PLACEHOLDER_HOST)
    for user in users:
        out = _replace_token(out, user, PLACEHOLDER_USER)
    # Device serial from live probe (identifying, rarely needed for remap bugs).
    out = re.sub(
        r"serial=(b)?(['\"])([^'\"]*)\2",
        rf"serial=\1\2{PLACEHOLDER_SERIAL}\2",
        out,
    )
    out = re.sub(
        r"(?im)^(\s*iSerial\s+\d+\s+).*$",
        rf"\1{PLACEHOLDER_SERIAL}",
        out,
    )
    return out
