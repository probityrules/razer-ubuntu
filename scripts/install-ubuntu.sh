#!/usr/bin/env bash
# Install tartarus-v2 on Ubuntu 26.x (also works on 24.04+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Installing system packages"
sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-gi \
  gir1.2-gtk-4.0 \
  gir1.2-adw-1 \
  gir1.2-ayatanaappindicator3-0.1 \
  libusb-1.0-0 \
  udev

echo "==> Creating venv at .venv (access system GI site-packages)"
python3 -m venv --system-site-packages .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e ".[linux,dev]"

echo "==> Installing udev rules"
sudo cp "$ROOT/scripts/99-tartarus-v2.rules" /etc/udev/rules.d/99-tartarus-v2.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "==> Installing desktop entry"
mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
# Prefer venv wrapper when present
DESKTOP_SRC="$ROOT/packaging/tartarus-v2.desktop"
DESKTOP_DST="${XDG_DATA_HOME:-$HOME/.local/share}/applications/tartarus-v2.desktop"
sed "s|^Exec=tartarus-v2 gui|Exec=$ROOT/.venv/bin/tartarus-v2 gui|; s|^Exec=tartarus-v2 uninstall|Exec=$ROOT/.venv/bin/tartarus-v2 uninstall|" \
  "$DESKTOP_SRC" > "$DESKTOP_DST"
update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications" 2>/dev/null || true

echo "==> Enabling login autostart for daemon"
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
sed "s|^Exec=.*|Exec=$ROOT/.venv/bin/tartarus-v2 daemon --background|" \
  "$ROOT/packaging/tartarus-v2-daemon.desktop" \
  > "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/tartarus-v2-daemon.desktop"

echo "==> Ensuring user groups (input, plugdev)"
USER_NAME="${SUDO_USER:-$USER}"
sudo usermod -aG input,plugdev "$USER_NAME" || true

if lsmod | grep -qi razerkbd; then
  echo ""
  echo "WARNING: OpenRazer razerkbd module is loaded."
  echo "It may block chroma USB control. Run diagnose from the GUI or CLI."
fi

echo ""
echo "Install complete."
echo "1) Log out and back in (or reboot) so group membership applies."
echo "2) Plug in the Tartarus V2."
echo "3) Open 'Tartarus V2' from the app grid, or:"
echo "     source $ROOT/.venv/bin/activate"
echo "     tartarus-v2 gui"
echo "4) Or CLI diagnose:"
echo "     tartarus-v2 diagnose --out ~/tartarus-diagnose.log"
echo "5) Run tests:"
echo "     pytest"
