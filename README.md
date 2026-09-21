# Tartarus V2 (Linux)

Standalone **userspace** driver for the **Razer Tartarus V2** (`1532:022B`) on Ubuntu 26 / modern Linux.

No OpenRazer runtime dependency. Supports RGB lighting, key remapping, **Hypershift**, macros, and profiles — plus a paste-ready `diagnose` dump for remote debugging (develop on Windows, test on Linux).

## Features

| Area | What you get |
|------|----------------|
| RGB | none, static, spectrum, wave, breath, reactive, starlight, custom frame; brightness 0–255 |
| Remap | keypad keys, thumb stick, scroll → key / combo |
| Hypershift | hold a configured key (default: `mode`) to activate a second binding layer |
| Macros | sequenced taps/presses with delays |
| Profiles | JSON profiles under `~/.cache/tartarus-v2/profiles/` |
| Diagnostics | `tartarus-v2 diagnose` → copy/paste log for remote debugging |

## Requirements

- Ubuntu 26.x (or 24.04+)
- Python 3.10+ (3.12+ recommended on Ubuntu 26)
- Razer Tartarus V2 plugged in over USB
- User in `input` and `plugdev` groups (installer handles this)

## Quick install (Linux)

```bash
git clone <this-repo> && cd razer-ubuntu
chmod +x scripts/install-ubuntu.sh
./scripts/install-ubuntu.sh
# log out/in (or reboot), then:
source .venv/bin/activate
tartarus-v2 diagnose --out ~/tartarus-diagnose.log
```

Paste the diagnose output (between `=== COPY FROM HERE ===` and `=== COPY TO HERE ===`) back into your development chat if something fails.

## Common commands

```bash
# System dump (always start here on a new machine)
tartarus-v2 diagnose --out ~/tartarus-diagnose.log
tartarus-v2 diagnose --listen 3          # also capture 3s of key events

# Lighting smoke test
tartarus-v2 set-effect static --rgb FF0000
tartarus-v2 set-effect spectrum
tartarus-v2 set-brightness 200
tartarus-v2 info

# Remap + Hypershift + lighting daemon
tartarus-v2 daemon --debug

# Profiles
tartarus-v2 profile list
tartarus-v2 profile show default
tartarus-v2 profile use default
```

## Hypershift

Each profile has:

- `hypershift_key` — logical key that activates the layer while held (default: `mode`)
- `standard.bindings` — normal map
- `hypershift.bindings` — secondary map (keys, combos, macros)

Example binding styles in JSON:

```json
"key_01": "1",
"key_02": "ctrl+c",
"key_03": { "type": "macro", "steps": [ { "tap": "ctrl+v" }, { "delay_ms": 40 } ] },
"scroll_up": { "type": "profile_next" }
```

Logical key names: `key_01`…`key_15`, `mode`, `thumb`, `stick_up` / `down` / `left` / `right`, `scroll_up` / `scroll_down`.

## OpenRazer conflict

This driver talks to the device with USB control transfers. If OpenRazer’s `razerkbd` module owns the device, chroma commands may fail.

`tartarus-v2 diagnose` section **5** detects this and prints unbind steps. You do **not** need OpenRazer installed for this project.

## Remote debug workflow

1. On Linux: `tartarus-v2 diagnose --out ~/tartarus-diagnose.log`
2. Copy everything between the `COPY FROM HERE` / `COPY TO HERE` banners
3. Paste into the Windows-side chat so the driver can be fixed without shell access to the test box

Daemon logs live at `~/.cache/tartarus-v2/tartarus-v2.log` (`--debug` adds HID hex and Hypershift enter/exit).

## Development (Windows)

Protocol and profile code can be edited on Windows. Hardware I/O (`pyusb`, `evdev`) only runs on Linux.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Architecture

```text
CLI / daemon
 ├── Chroma (pyusb control transfers, 90-byte Razer reports)
 └── Remapper (evdev grab → uinput), Hypershift + macros
```

Protocol framing is compatible with the public OpenRazer keyboard path for Tartarus V2 (extended matrix, `transaction_id` `0x1F`, brightness via `ZERO_LED`). This repo does not link against or require OpenRazer at runtime.

## License

MIT. Protocol details referenced from the OpenRazer project (GPL-2.0) for interoperability; this userspace implementation is original code under MIT.
