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
| Permissions | `fix-permissions` | Device / Daemon → Fix permissions |
| Diagnostics | `tartarus-v2 diagnose` | Diagnose page (copy/save) |
| GUI | `tartarus-v2 gui` | App grid / tray |

## Requirements

- Ubuntu 26.x (or 24.04+) with GNOME
- Python 3.10+ (system `python3-gi`, GTK4, Libadwaita, Ayatana AppIndicator)
- Razer Tartarus V2 over USB
- User in `input` and `plugdev` groups (installer / `fix-permissions` adds these)

## Quick install (Linux)

### From GitHub Releases (recommended)

On each version bump to `main`, CI builds a `.deb` and attaches it to a GitHub Release (`vX.Y.Z`):

```bash
# Example for v0.6.1 — use the latest release tag/assets from GitHub:
curl -LO "https://github.com/probityrules/razer-ubuntu/releases/latest/download/tartarus-v2_0.6.1_all.deb"
sudo apt install ./tartarus-v2_0.6.1_all.deb
# postinst adds you to input+plugdev when it can detect your user
# log out/in, then:
tartarus-v2 gui
# If remapping still fails (Permission denied on /dev/input):
tartarus-v2 fix-permissions   # or Device/Daemon → Fix permissions in the GUI
```

(Exact `.deb` filename matches the release version.)

### From source

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
3. **Profiles** — activate / add profile; **Advanced…** for JSON, duplicate, folder
4. **Bindings** — layout with Normal + Hypershift per key, live press highlight, draft edits + **Apply all**
5. **Daemon** — start/stop, **Start at login** autostart, debug toggle, **Fix permissions**
6. **Diagnose** — live EV_KEY listen (daemon pauses on this page, restarts when you leave), dump/copy/save

The header shows a persistent **daemon LED** (green = running, grey = stopped). Device info refreshes automatically while that page is open.

App menu → **Report issue…** opens a Notefully-style dialog (kind, author, note). Submits to your Notefully relay with a diagnose dump and log tail attached in the report context (no screenshots).

Release `.deb` builds embed the public project key from the GitHub Actions repository variable **`NOTEFULLY_PROJECT_KEY`** (optional **`NOTEFULLY_ENDPOINT`**). Overrides still work:

- Env: `TARTARUS_NOTEFULLY_KEY` (and optional `TARTARUS_NOTEFULLY_ENDPOINT`)
- Or `~/.config/tartarus-v2/notefully.json` → `{ "projectKey": "nfk_…" }`
- Default endpoint: `https://make.makefullystudios.com/notefully`

If no key is baked in or configured, the dialog asks for one and saves it under that config path.

Device and Daemon pages warn when you are missing `input`/`plugdev` and offer **Fix permissions** (polkit/`pkexec`). The `.deb` postinst also tries to add the installing user to those groups automatically.

Tray / app-grid right-click: **Uninstall** (`.deb` via `pkexec apt-get remove`). Login autostart runs `tartarus-v2 daemon --background` (packaged under `/etc/xdg/autostart/`, toggleable from Daemon).

## CLI

```bash
tartarus-v2 diagnose --out ~/tartarus-diagnose.log
tartarus-v2 diagnose --listen 3
tartarus-v2 set-effect static --rgb FF0000
tartarus-v2 set-brightness 200
tartarus-v2 info
tartarus-v2 daemon --debug
tartarus-v2 fix-permissions
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

## Packaging (.deb)

On Ubuntu/Debian (or CI):

```bash
chmod +x packaging/build-deb.sh
NOTEFULLY_PROJECT_KEY='nfk_…' ./packaging/build-deb.sh   # optional embed
# → dist/tartarus-v2_<version>_all.deb
```

Pushing a **version bump** on `main` (see `bcp`) triggers `.github/workflows/release-deb.yml`, which builds the `.deb` and publishes a GitHub Release. CI embeds `vars.NOTEFULLY_PROJECT_KEY` when that repository variable is set.

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
