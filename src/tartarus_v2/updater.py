"""Check GitHub Releases for a newer tartarus-v2 .deb and install it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from tartarus_v2 import __version__
from tartarus_v2.logging_util import cache_dir

GITHUB_REPO = "probityrules/razer-ubuntu"
LATEST_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_USER_AGENT = f"tartarus-v2/{__version__}"
_DOWNLOAD_PREFIX = f"https://github.com/{GITHUB_REPO}/releases/download/"


@dataclass(frozen=True)
class UpdateCheck:
    current: str
    latest: str | None
    update_available: bool
    asset_url: str | None
    asset_name: str | None
    html_url: str | None
    detail: str


def parse_version(text: str) -> tuple[int, ...]:
    raw = text.strip()
    if raw[:1].lower() == "v":
        raw = raw[1:]
    parts: list[int] = []
    for piece in raw.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    if not parts:
        raise ValueError(f"Unparseable version: {text!r}")
    return tuple(parts)


def _fetch_latest(timeout: float = 20.0) -> dict:
    req = urllib.request.Request(
        LATEST_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub release response was not an object")
    return payload


def _deb_asset(payload: dict, version: str) -> tuple[str | None, str | None]:
    expected = f"tartarus-v2_{version}_all.deb"
    assets = payload.get("assets") or []
    if not isinstance(assets, list):
        return None, None
    fallback: tuple[str | None, str | None] = (None, None)
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if name == expected and url:
            return name, url
        if name.endswith("_all.deb") and url and fallback[0] is None:
            fallback = (name, url)
    return fallback


def check_for_update(current: str | None = None, timeout: float = 20.0) -> UpdateCheck:
    current = current or __version__
    try:
        payload = _fetch_latest(timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return UpdateCheck(
            current=current,
            latest=None,
            update_available=False,
            asset_url=None,
            asset_name=None,
            html_url=None,
            detail=f"Could not check for updates: {exc}",
        )

    tag = str(payload.get("tag_name") or "").strip()
    html = str(payload.get("html_url") or "") or None
    try:
        latest = tag[1:] if tag.lower().startswith("v") else tag
        if not latest:
            raise ValueError("release has no tag")
        newer = parse_version(latest) > parse_version(current)
    except ValueError as exc:
        return UpdateCheck(
            current=current,
            latest=None,
            update_available=False,
            asset_url=None,
            asset_name=None,
            html_url=html,
            detail=f"Could not compare versions ({exc}).",
        )

    name, url = _deb_asset(payload, latest)
    if not newer:
        return UpdateCheck(
            current=current,
            latest=latest,
            update_available=False,
            asset_url=url,
            asset_name=name,
            html_url=html,
            detail=f"Tartarus V2 {current} is up to date (latest release {latest}).",
        )
    if not url:
        return UpdateCheck(
            current=current,
            latest=latest,
            update_available=True,
            asset_url=None,
            asset_name=None,
            html_url=html,
            detail=(
                f"Version {latest} is available but the release has no .deb asset. "
                f"See {html or LATEST_API}."
            ),
        )
    return UpdateCheck(
        current=current,
        latest=latest,
        update_available=True,
        asset_url=url,
        asset_name=name,
        html_url=html,
        detail=f"Update available: {current} → {latest}.",
    )


def _safe_asset_url(url: str) -> bool:
    return url.startswith(_DOWNLOAD_PREFIX) and "://" in url and url.lower().startswith("https://")


def install_update(info: UpdateCheck, timeout: float = 60.0) -> str:
    """Download the release .deb and install it with pkexec/apt (admin once)."""
    if not info.update_available:
        return info.detail or "Already up to date."
    if not info.asset_url or not info.latest:
        return info.detail or "No downloadable update."
    if not _safe_asset_url(info.asset_url):
        return f"Refusing to download unexpected URL: {info.asset_url}"

    name = info.asset_name or f"tartarus-v2_{info.latest}_all.deb"
    dest = cache_dir() / name
    try:
        req = urllib.request.Request(info.asset_url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"Update failed: could not download {info.asset_url}: {exc}"

    apt = shutil.which("apt-get") or shutil.which("apt")
    if not apt:
        return (
            f"Downloaded {dest} but apt-get was not found. "
            f"Install it with: sudo apt install {dest}"
        )

    cmd = [apt, "install", "-y", str(dest)]
    pkexec = shutil.which("pkexec")
    sudo = shutil.which("sudo")
    if os_euid_is_root():
        pass
    elif pkexec:
        cmd = [pkexec, *cmd]
    elif sudo:
        cmd = [sudo, *cmd]
    else:
        return (
            f"Downloaded {dest}. pkexec/sudo not found. "
            f"Install with: sudo apt install {dest}   then restart Tartarus V2."
        )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return f"Update failed: {exc}"

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return f"Update failed (code {proc.returncode}): {err[:500]}"
    return (
        f"Installed tartarus-v2 {info.latest}. "
        "Quit and reopen Tartarus V2 to use the new version."
    )


def os_euid_is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return False
    try:
        return bool(geteuid() == 0)
    except OSError:
        return False
