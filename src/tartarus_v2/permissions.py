"""Check and fix Linux input/plugdev access for remapping.

The remap daemon does not need to run as root. It needs to exclusive-grab the
keypad and create a uinput virtual keyboard (``/dev/uinput``). Without that
node, the daemon exits and text editors keep the firmware's default keys.
"""

from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

REQUIRED_GROUPS: tuple[str, ...] = ("input", "plugdev")

# Installed by the .deb and ensured by fix-permissions. uaccess lets the
# active desktop session write /dev/uinput without a root daemon.
UINPUT_RULE = (
    'KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="input", '
    'TAG+="uaccess", OPTIONS+="static_node=uinput"'
)

_USER_RE = re.compile(r"[A-Za-z0-9._-]+")


@dataclass(frozen=True)
class PermissionStatus:
    user: str
    groups: tuple[str, ...]
    missing: tuple[str, ...]
    ok: bool
    detail: str
    needs_relogin: bool = False


def current_username() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def session_group_names() -> set[str]:
    """Groups this process actually has (not merely /etc/group membership)."""
    names: set[str] = set()
    try:
        import grp

        try:
            names.add(grp.getgrgid(os.getgid()).gr_name)
        except KeyError:
            pass
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


def database_group_names(username: str) -> set[str]:
    """Groups recorded for ``username`` in the group database (after usermod)."""
    names: set[str] = set()
    try:
        import grp

        for g in grp.getgrall():
            if username in g.gr_mem:
                names.add(g.gr_name)
        try:
            import pwd

            primary = pwd.getpwnam(username).pw_gid
            names.add(grp.getgrgid(primary).gr_name)
        except (KeyError, ImportError):
            pass
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        pass
    return names


def user_group_names(username: str | None = None) -> set[str]:
    """Effective groups for permission checks.

    For the current user this is the login session, because a group added by
    usermod does not apply until the next login. Checking only /etc/group
    reports success while /dev/uinput is still permission-denied.
    """
    user = username or current_username()
    if user == current_username():
        return session_group_names()
    return database_group_names(user)


def uinput_status() -> tuple[bool, str]:
    """Whether this process can create the virtual keyboard node."""
    path = "/dev/uinput"
    if not os.path.exists(path):
        return False, (
            "/dev/uinput is missing, so the remap daemon cannot inject keys and "
            "text editors keep the keypad's default layout. "
            "Root is not required: run tartarus-v2 fix-permissions "
            "(loads the uinput module)."
        )
    if os.access(path, os.W_OK):
        return True, "/dev/uinput is writable (virtual keyboard can be created)"
    return False, (
        "/dev/uinput is not writable by this login. The remap daemon exits "
        "before it can grab the keypad, so text editors keep the default keys. "
        "Root is not required — run tartarus-v2 fix-permissions, then log out "
        "and back in if this session still lacks the input group."
    )


def permission_status(username: str | None = None) -> PermissionStatus:
    user = username or current_username()
    groups = tuple(sorted(user_group_names(user)))
    missing = tuple(g for g in REQUIRED_GROUPS if g not in groups)
    db = database_group_names(user) if user == current_username() else set(groups)
    needs_relogin = bool(missing) and all(g in db for g in missing)
    uinput_ok, uinput_detail = uinput_status()
    ok = not missing and uinput_ok

    parts: list[str] = []
    if not missing:
        parts.append(f"{user} is in {', '.join(REQUIRED_GROUPS)} in this session")
    elif needs_relogin:
        parts.append(
            f"{user} is in {', '.join(missing)} in the account database, but this "
            "login session does not have those groups yet. Log out and back in. "
            "The driver does not need to run as root."
        )
    else:
        parts.append(
            f"{user} missing group(s): {', '.join(missing)}. "
            "Remapping needs 'input' (and /dev/uinput); chroma/hidraw needs 'plugdev'. "
            "Root is not required."
        )
    parts.append(uinput_detail)
    return PermissionStatus(
        user=user,
        groups=groups,
        missing=missing,
        ok=ok,
        detail=" ".join(parts),
        needs_relogin=needs_relogin,
    )


def _privileged_script(user: str) -> str:
    rule = UINPUT_RULE
    return f"""set -e
usermod -aG input,plugdev {user}
modprobe uinput || true
RULE_LINE='{rule}'
for rules in /etc/udev/rules.d/99-tartarus-v2.rules /lib/udev/rules.d/99-tartarus-v2.rules /usr/lib/udev/rules.d/99-tartarus-v2.rules; do
  dir=$(dirname "$rules")
  if [ ! -d "$dir" ]; then
    continue
  fi
  if [ -f "$rules" ] && grep -q 'KERNEL=="uinput"' "$rules"; then
    continue
  fi
  if [ -f "$rules" ]; then
    printf '\\n%s\\n' "$RULE_LINE" >> "$rules"
  else
    printf '%s\\n' "$RULE_LINE" > "$rules"
  fi
done
udevadm control --reload-rules || true
udevadm trigger || true
"""


def _success_message(user: str) -> str:
    return (
        f"Added {user} to input,plugdev, loaded uinput, and reloaded udev. "
        "The remap daemon does not need to run as root. "
        "Log out and back in (required if this session was missing the input group), "
        "then start the daemon so text editors receive remapped keys."
    )


def _run_elevated(cmd: list[str]) -> str:
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
    return ""


def fix_permissions(username: str | None = None) -> str:
    """Add the user to input+plugdev, ensure /dev/uinput, and reload udev."""
    status = permission_status(username)
    user = status.user
    if user in ("unknown", "root"):
        return "Cannot fix groups for this account; run as your desktop user."
    if not _USER_RE.fullmatch(user):
        return f"Refusing to change groups for unexpected username {user!r}."

    if status.ok:
        return (
            f"{user} is already in input and plugdev, and /dev/uinput is writable. "
            "The remap daemon does not need root. "
            "If remapping still fails, log out/in (or reboot) and unplug/replug the Tartarus."
        )

    script = _privileged_script(user)
    if os.name != "nt" and os.geteuid() == 0:
        err = _run_elevated(["sh", "-c", script])
        return err or _success_message(user)

    pkexec = shutil.which("pkexec")
    sudo = shutil.which("sudo")
    if pkexec:
        cmd = [pkexec, "sh", "-c", script]
    elif sudo:
        cmd = [sudo, "sh", "-c", script]
    else:
        return (
            f"pkexec/sudo not found. Run as root:\n"
            f"  usermod -aG input,plugdev {user}\n"
            f"  modprobe uinput\n"
            f"  udevadm control --reload-rules && udevadm trigger\n"
            f"Then log out and back in. The driver itself does not need to stay running as root."
        )

    err = _run_elevated(cmd)
    return err or _success_message(user)


def _apply_as_root(user: str) -> str:
    """Backward-compatible entry used by tests and older callers."""
    if not _USER_RE.fullmatch(user):
        return f"Refusing to change groups for unexpected username {user!r}."
    err = _run_elevated(["sh", "-c", _privileged_script(user)])
    return err or _success_message(user)
