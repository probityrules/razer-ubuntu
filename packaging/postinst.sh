#!/bin/sh
set -e
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

echo "tartarus-v2: installed. Run: tartarus-v2 gui"
echo "  If remapping fails: tartarus-v2 fix-permissions"
