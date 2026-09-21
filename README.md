# Tartarus V2 (Linux)

Standalone **userspace** driver for the **Razer Tartarus V2** (`1532:022B`) on Ubuntu 26 / modern Linux.

No OpenRazer runtime dependency. Supports RGB lighting, key remapping, **Hypershift**, macros, profiles, a **GTK4 / Libadwaita GUI**, and a paste-ready `diagnose` dump for remote debugging.

## Features

| Area | CLI | GUI |
|------|-----|-----|
| Device info | `tartarus-v2 info` | Device page |
| RGB / brightness | `set-effect`, `set-brightness` | Lighting page |
| Profiles | `profile list/show/use/path` | Profiles page |
| Remap + Hypershift + macros | profile JSON + daemon | Bindings page |
| Daemon | `tartarus-v2 daemon` | Daemon page + tray |
| Diagnostics | `tartarus-v2 diagnose` | Diagnose page (copy/save) |
| GUI | `tartarus-v2 gui` | App grid / tray |

## Requirements

- Ubuntu 26.x (or 24.04+) with GNOME
- Python 3.10+ (system `python3-gi`, GTK4, Libadwaita, Ayatana AppIndicator)
- Razer Tartarus V2 over USB
- User in `input` and `plugdev` groups

## Quick install (Linux)

```bash
git clone <this-repo> && cd razer-ubuntu
chmod +x scripts/install-ubuntu.sh
./scripts/install-ubuntu.sh
# log out/in, then:
source .venv/bin/activate
tartarus-v2 gui
# or:
tartarus-v2 diagnose --out ~/tartarus-diagnose.log
```

The installer adds a **Tartarus V2** desktop entry. The GUI uses system tray (AppIndicator) for start/stop daemon and profile cycling.

## GUI overview

Native **Libadwaita** app (`Adw.Application` + sidebar navigation):

1. **Device** — firmware / serial / brightness (`info`)
2. **Lighting** — effects, colours, brightness (`set-effect` / `set-brightness`)
3. **Profiles** — list, activate, duplicate, open folder, JSON preview
4. **Bindings** — Standard / Hypershift layers, hypershift key, macros
5. **Daemon** — start/stop remap subprocess with debug toggle
6. **Diagnose** — run dump, copy clipboard, save file (COPY banners)

## CLI

```bash
tartarus-v2 diagnose --out ~/tartarus-diagnose.log
tartarus-v2 diagnose --listen 3
tartarus-v2 set-effect static --rgb FF0000
tartarus-v2 set-brightness 200
tartarus-v2 info
tartarus-v2 daemon --debug
tartarus-v2 profile list
tartarus-v2 gui
```

## Hypershift

Each profile has `hypershift_key`, `standard.bindings`, and `hypershift.bindings`. Edit in the GUI Bindings page or JSON under `~/.cache/tartarus-v2/profiles/`.

## Tests and coverage

Parity tests enforce every CLI command has a matching GUI controller handler (`FEATURE_MAP`). Coverage gate is **85%** on the core package (hardware/GI widgets omitted).

```bash
pip install -e ".[dev]"
pytest
```

On Ubuntu with GI installed you can also explore the GUI manually via `tartarus-v2 gui`.

## OpenRazer conflict

If OpenRazer’s `razerkbd` owns the device, chroma may fail. Diagnose section 5 prints unbind steps. This project does **not** require OpenRazer.

## Remote debug workflow

1. GUI **Diagnose** → Run → Copy, or `tartarus-v2 diagnose --out ~/tartarus-diagnose.log`
2. Paste between `=== COPY FROM HERE ===` and `=== COPY TO HERE ===`
3. Iterate from the Windows-side chat

## Development (Windows)

Edit protocol/actions/GUI controllers on Windows. Hardware I/O and the Libadwaita UI run on Linux.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Architecture

```text
CLI / GUI controllers
 ├── actions.py (shared)
 ├── daemon_control.py (subprocess daemon)
 ├── Chroma (pyusb, 90-byte reports)
 └── Remapper (evdev → uinput), Hypershift + macros
```

## License

MIT. Protocol details referenced from OpenRazer (GPL-2.0) for interoperability; this userspace implementation is original code under MIT.
