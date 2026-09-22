#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload-rules || true
  udevadm trigger || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
echo "tartarus-v2: installed. Add your user to groups 'input' and 'plugdev', then log out/in:"
echo "  sudo usermod -aG input,plugdev \"\$USER\""
echo "Then run: tartarus-v2 gui   or   tartarus-v2 diagnose"
