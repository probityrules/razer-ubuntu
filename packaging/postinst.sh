#!/bin/sh
set -e
if command -v modprobe >/dev/null 2>&1; then
  modprobe uinput || true
fi
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload-rules || true
  udevadm trigger || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi

# Add the user who ran `sudo apt install` to input + plugdev (one-time setup).
TARGET_USER="${SUDO_USER:-}"
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
  TARGET_USER="$(logname 2>/dev/null || true)"
fi
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
  # Last resort: owner of the active graphical seat display, if any
  TARGET_USER="$(who 2>/dev/null | awk 'NR==1 {print $1; exit}')"
fi

if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ] && id "$TARGET_USER" >/dev/null 2>&1; then
  if command -v usermod >/dev/null 2>&1; then
    usermod -aG input,plugdev "$TARGET_USER" || true
    echo "tartarus-v2: added user '$TARGET_USER' to groups input,plugdev."
    echo "tartarus-v2: log out and back in (or reboot) so remapping can open /dev/input."
  fi
else
  echo "tartarus-v2: could not detect install user. Add yourself to input,plugdev:"
  echo "  sudo usermod -aG input,plugdev \"\$USER\""
  echo "Then log out/in."
fi

# Start the remap daemon at graphical login. systemctl --global enable writes
# the wants symlink for every user; XDG autostart then no-ops if this unit
# is enabled so the daemon is not launched twice.
if command -v systemctl >/dev/null 2>&1; then
  systemctl --global enable tartarus-v2.service >/dev/null 2>&1 || true
  if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ]; then
    if command -v runuser >/dev/null 2>&1; then
      TARGET_UID="$(id -u "$TARGET_USER" 2>/dev/null || true)"
      if [ -n "$TARGET_UID" ] && [ -d "/run/user/$TARGET_UID" ]; then
        runuser -u "$TARGET_USER" --env "XDG_RUNTIME_DIR=/run/user/$TARGET_UID" -- \
          systemctl --user daemon-reload >/dev/null 2>&1 || true
        runuser -u "$TARGET_USER" --env "XDG_RUNTIME_DIR=/run/user/$TARGET_UID" -- \
          systemctl --user enable tartarus-v2.service >/dev/null 2>&1 || true
      else
        runuser -u "$TARGET_USER" -- systemctl --user daemon-reload >/dev/null 2>&1 || true
        runuser -u "$TARGET_USER" -- systemctl --user enable tartarus-v2.service >/dev/null 2>&1 || true
      fi
    fi
  fi
fi

echo "tartarus-v2: installed. Run: tartarus-v2 gui"
echo "  If remapping fails: tartarus-v2 fix-permissions"

# Best-effort: fully restart the installing user's remap daemon so upgrades
# drop any leftover in-memory remapper (systemd unit and/or PID-file process).
if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ] && command -v tartarus-v2 >/dev/null 2>&1; then
  TARGET_UID="$(id -u "$TARGET_USER" 2>/dev/null || true)"
  if command -v runuser >/dev/null 2>&1; then
    if [ -n "$TARGET_UID" ] && [ -d "/run/user/$TARGET_UID" ]; then
      runuser -u "$TARGET_USER" --env "XDG_RUNTIME_DIR=/run/user/$TARGET_UID" -- \
        tartarus-v2 daemon --restart >/dev/null 2>&1 || true
    else
      runuser -u "$TARGET_USER" -- tartarus-v2 daemon --restart >/dev/null 2>&1 || true
    fi
    echo "tartarus-v2: restarted remap daemon for '$TARGET_USER' (systemd and/or background)."
  elif command -v su >/dev/null 2>&1; then
    su - "$TARGET_USER" -c "tartarus-v2 daemon --restart >/dev/null 2>&1 || true" || true
    echo "tartarus-v2: attempted remap daemon restart for '$TARGET_USER'."
  fi
  echo "tartarus-v2: if keys stay dead after upgrade: tartarus-v2 daemon --restart"
  echo "  or log out/in (reboot also works)."
fi
