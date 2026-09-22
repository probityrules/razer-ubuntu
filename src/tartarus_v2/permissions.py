"""Check and fix Linux input/plugdev group membership for remapping."""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from dataclasses import dataclass


REQUIRED_GROUPS: tuple[str, ...] = ("input", "plugdev")


@dataclass(frozen=True)
class PermissionStatus:
    user: str
    groups: tuple[str, ...]
    missing: tuple[str, ...]
    ok: bool
    detail: str


def current_username() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def user_group_names(username: str | None = None) -> set[str]:
    user = username or current_username()
    names: set[str] = set()
    try:
        import grp

        for g in grp.getgrall():
            if user in g.gr_mem:
                names.add(g.gr_name)
        try:
            names.add(grp.getgrgid(os.getgid()).gr_name)
        except KeyError:
            pass
        # Also resolve supplemental groups from the process when checking self.
        if user == current_username():
            for gid in os.getgroups():
                try:
                    names.add(grp.getgrgid(gid).gr_name)
                except KeyError:
                    continue
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        pass
    return names


def permission_status(username: str | None = None) -> PermissionStatus:
    user = username or current_username()
    groups = tuple(sorted(user_group_names(user)))
    missing = tuple(g for g in REQUIRED_GROUPS if g not in groups)
    if not missing:
        detail = f"{user} is in {', '.join(REQUIRED_GROUPS)}"
        return PermissionStatus(user=user, groups=groups, missing=(), ok=True, detail=detail)
    detail = (
        f"{user} missing group(s): {', '.join(missing)}. "
        "Remapping needs 'input'; chroma/hidraw needs 'plugdev'."
    )
    return PermissionStatus(user=user, groups=groups, missing=missing, ok=False, detail=detail)


def fix_permissions(username: str | None = None) -> str:
    """Add the user to input+plugdev (via pkexec/sudo) and reload udev rules."""
    status = permission_status(username)
    user = status.user
    if user in ("unknown", "root"):
        return "Cannot fix groups for this account; run as your desktop user."

    if status.ok:
        return (
            f"{user} is already in input and plugdev. "
            "If remapping still fails, log out/in (or reboot) so the new session picks up groups, "
            "then unplug/replug the Tartarus."
        )

    if os.name != "nt" and os.geteuid() == 0:
        return _apply_as_root(user)

    pkexec = shutil.which("pkexec")
    sudo = shutil.which("sudo")
    if pkexec:
        # Single elevated shell: usermod + udev reload/trigger.
        script = (
            f"usermod -aG input,plugdev {user} && "
            "udevadm control --reload-rules && udevadm trigger"
        )
        cmd = [pkexec, "sh", "-c", script]
    elif sudo:
        cmd = [
            sudo,
            "sh",
            "-c",
            f"usermod -aG input,plugdev {user} && "
            "udevadm control --reload-rules && udevadm trigger",
        ]
    else:
        return (
            f"pkexec/sudo not found. Run as root:\n"
            f"  usermod -aG input,plugdev {user}\n"
            f"  udevadm control --reload-rules && udevadm trigger\n"
            f"Then log out and back in."
        )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return f"Permission fix failed: {exc}"

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return f"Permission fix failed (code {proc.returncode}): {err[:500]}"

    return (
        f"Added {user} to input,plugdev and reloaded udev. "
        "Log out and back in (required), then unplug/replug the Tartarus."
    )


def _apply_as_root(user: str) -> str:
    try:
        um = subprocess.run(
            ["usermod", "-aG", "input,plugdev", user],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if um.returncode != 0:
            err = (um.stderr or um.stdout or "").strip()
            return f"usermod failed: {err[:500]}"
        subprocess.run(
            ["udevadm", "control", "--reload-rules"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        subprocess.run(
            ["udevadm", "trigger"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return f"Permission fix failed: {exc}"
    return (
        f"Added {user} to input,plugdev and reloaded udev. "
        "Log out and back in (required), then unplug/replug the Tartarus."
    )
