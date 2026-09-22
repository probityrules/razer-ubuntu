# Debian packaging

## Build locally (Ubuntu/Debian)

```bash
chmod +x packaging/build-deb.sh packaging/postinst.sh packaging/postrm.sh
./packaging/build-deb.sh
# → dist/tartarus-v2_<version>_all.deb
sudo apt install ./dist/tartarus-v2_*.deb
```

The package:

- Installs the app under `/usr/lib/tartarus-v2/site-packages`
- Puts `tartarus-v2` on `PATH` via `/usr/bin/tartarus-v2`
- Installs udev rules and a desktop entry
- Depends on distro packages for `python3-usb`, `python3-evdev`, GTK4/Libadwaita GI, etc.

## CI release

`.github/workflows/release-deb.yml` runs on every push to `main`. If `pyproject.toml` version changed vs the previous commit, it builds the `.deb` and creates GitHub Release `v<version>` with the artifact attached.
