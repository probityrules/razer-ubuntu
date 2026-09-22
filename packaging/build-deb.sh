#!/usr/bin/env bash
# Build an amd64/all .deb for tartarus-v2 (run on Ubuntu/Debian).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 - <<'PY'
import tomllib
from pathlib import Path
print(tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
PY
)"

STAGE="${ROOT}/dist/deb-root"
OUT_DIR="${ROOT}/dist"
DEB_NAME="tartarus-v2_${VERSION}_all.deb"

echo "==> Building tartarus-v2 ${VERSION} .deb"

rm -rf "${STAGE}"
mkdir -p \
  "${STAGE}/DEBIAN" \
  "${STAGE}/usr/bin" \
  "${STAGE}/usr/lib/tartarus-v2/site-packages" \
  "${STAGE}/usr/share/applications" \
  "${STAGE}/lib/udev/rules.d" \
  "${OUT_DIR}"

python3 -m pip install --upgrade pip
python3 -m pip install . --no-deps --target "${STAGE}/usr/lib/tartarus-v2/site-packages"

# CLI/GUI launcher (system python3 + bundled package; GI from distro)
cat > "${STAGE}/usr/bin/tartarus-v2" <<'EOF'
#!/bin/sh
export PYTHONPATH="/usr/lib/tartarus-v2/site-packages${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m tartarus_v2 "$@"
EOF
chmod 755 "${STAGE}/usr/bin/tartarus-v2"

install -m 644 "${ROOT}/scripts/99-tartarus-v2.rules" \
  "${STAGE}/lib/udev/rules.d/99-tartarus-v2.rules"
install -m 644 "${ROOT}/packaging/tartarus-v2.desktop" \
  "${STAGE}/usr/share/applications/tartarus-v2.desktop"

cat > "${STAGE}/DEBIAN/control" <<EOF
Package: tartarus-v2
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: tartarus-v2 contributors <noreply@users.noreply.github.com>
Homepage: https://github.com/probityrules/razer-ubuntu
Depends: python3 (>= 3.10), python3-usb, python3-evdev, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-ayatanaappindicator3-0.1, libusb-1.0-0, udev
Recommends: python3-gi
Description: Userspace driver for Razer Tartarus V2
 Standalone Linux userspace stack for the Razer Tartarus V2 keypad:
 RGB lighting, remapping, Hypershift, macros, profiles, GTK4/Libadwaita
 GUI, and paste-ready diagnostics. No OpenRazer runtime dependency.
EOF

install -m 755 "${ROOT}/packaging/postinst.sh" "${STAGE}/DEBIAN/postinst"
install -m 755 "${ROOT}/packaging/postrm.sh" "${STAGE}/DEBIAN/postrm"

# Drop pip metadata noise from package size if present
find "${STAGE}/usr/lib/tartarus-v2/site-packages" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

dpkg-deb --root-owner-group --build "${STAGE}" "${OUT_DIR}/${DEB_NAME}"

echo "==> Built ${OUT_DIR}/${DEB_NAME}"
dpkg-deb -I "${OUT_DIR}/${DEB_NAME}"
ls -lh "${OUT_DIR}/${DEB_NAME}"
