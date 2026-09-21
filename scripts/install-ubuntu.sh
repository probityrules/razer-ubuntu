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
  libusb-1.0-0 \
  udev

echo "==> Creating venv at .venv"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e ".[linux]"

echo "==> Installing udev rules"
sudo cp "$ROOT/scripts/99-tartarus-v2.rules" /etc/udev/rules.d/99-tartarus-v2.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "==> Ensuring user groups (input, plugdev)"
USER_NAME="${SUDO_USER:-$USER}"
sudo usermod -aG input,plugdev "$USER_NAME" || true

if lsmod | grep -qi razerkbd; then
  echo ""
  echo "WARNING: OpenRazer razerkbd module is loaded."
  echo "It may block chroma USB control. Run: tartarus-v2 diagnose"
  echo "and follow the unbind steps in section 5 if lighting fails."
fi

echo ""
echo "Install complete."
echo "1) Log out and back in (or reboot) so group membership applies."
echo "2) Plug in the Tartarus V2."
echo "3) Run:"
echo "     source $ROOT/.venv/bin/activate"
echo "     tartarus-v2 diagnose --out ~/tartarus-diagnose.log"
echo "4) Start the daemon:"
echo "     tartarus-v2 daemon --debug"
