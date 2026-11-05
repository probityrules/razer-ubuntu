# Changelog

All notable changes to tartarus-v2 are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.18.1] - 2026-11-05

### Fixed

- Point the README install one-liner at a stable `tartarus-v2_latest_all.deb` asset so `/releases/latest/download/` no longer 404s.

### Added

- Backfilled `CHANGELOG.md` and include each version’s notes in GitHub Release posts.

## [0.18.0] - 2026-11-04

### Added

- Profile deletion on the Profiles page and in the CLI.

## [0.17.2] - 2026-09-28

### Fixed

- Release keys with press-time output codes so Hypershift layer changes cannot stick them.

## [0.17.1] - 2026-09-28

### Changed

- Match scroll keymap buttons to the same filled grey as pad keys.

## [0.17.0] - 2026-09-28

### Added

- Per-profile red/green/blue mode LED toggles on the Lighting page.

## [0.16.0] - 2026-09-28

### Added

- GTK4 StatusNotifier tray with active profile label.
- Restart an open GUI on package upgrade.

## [0.15.2] - 2026-09-28

### Fixed

- Emit scroll on a virtual mouse and keep remapping after ENODEV on wheel write.

## [0.15.1] - 2026-09-28

### Changed

- Higher-saturation 5×8 palette in the lighting colour picker.

## [0.15.0] - 2026-09-25

### Changed

- Redact username, hostname, and home paths from diagnose reports.

## [0.14.2] - 2026-09-25

### Fixed

- Apply profile lighting to the pad when switching profiles.

## [0.14.1] - 2026-09-25

### Fixed

- Emit scroll bindings as wheel events and block wrong Insert kinds.

## [0.14.0] - 2026-09-25

### Changed

- Draw the scroll wheel as one capsule and match the keymap wireframe.

## [0.13.1] - 2026-09-25

### Fixed

- Restart systemd and background remappers cleanly on package upgrade.

## [0.13.0] - 2026-09-25

### Changed

- Lay out the Bindings keymap like the physical Tartarus.

## [0.12.0] - 2026-09-25

### Added

- Show the active profile on the tray/panel indicator.

## [0.11.0] - 2026-09-25

### Changed

- Keymap keys are filled tiles with colored Normal and Hypershift labels.

## [0.10.0] - 2026-09-25

### Added

- Insert key/command picker for Normal and Hypershift bindings.

## [0.9.1] - 2026-09-25

### Fixed

- Always persist lighting to the profile and align Lighting profile switching with Bindings.

## [0.9.0] - 2026-09-25

### Changed

- Reserve Hypershift on the keymap and tighten Bindings/Daemon/Diagnose UI.

## [0.8.2] - 2026-09-24

### Fixed

- Keep the second Tartarus keyboard bound so keys are remapped.

## [0.8.1] - 2026-09-24

### Fixed

- Keep the keypad alive across Diagnose and Daemon.

## [0.8.0] - 2026-09-24

### Changed

- Restart remap daemon on upgrade and relaunch GUI after in-app update.

## [0.7.5] - 2026-09-24

### Fixed

- Recalibrate physical EV_KEY map from live Tartarus evtest.

## [0.7.4] - 2026-09-24

### Fixed

- Ship the remap and Check for updates menu fix that missed 0.7.3.

## [0.7.3] - 2026-09-24

### Fixed

- Key 20 is the thumb key, not a fifth keypad key.
- Send remapped keys to other apps.

### Added

- App menu → Check for updates.

## [0.7.2] - 2026-09-24

### Fixed

- Bindings Apply starts the system-wide remap daemon and fails hard without grab.

## [0.7.1] - 2026-09-23

### Changed

- Clearer visuals for the active profile.

## [0.7.0] - 2026-09-23

### Changed

- Diagnose listen uses physical/virtual highlight logic with a manual daemon toggle.

## [0.6.2] - 2026-09-23

### Fixed

- Report issue dialog open crash; add wiring/smoke tests.

## [0.6.1] - 2026-09-22

### Fixed

- Isolate profile bindings so edits do not cross profiles.

## [0.6.0] - 2026-09-22

### Added

- Bindings layout/highlight, daemon LED, richer Notefully reports.

## [0.5.1] - 2026-09-22

### Changed

- Show Report issue Submit in a bottom action bar.

## [0.5.0] - 2026-09-22

### Added

- Report issue via Notefully with CI-baked project key.

## [0.4.0] - 2026-09-22

### Added

- Live key listen and Bindings Apply workflow.

## [0.3.1] - 2026-09-22

### Added

- Live daemon reload, GUI errors, and full 5×4 keymap.

## [0.3.0] - 2026-09-22

### Added

- Bindings/profiles UX, autostart, uninstall, and fix-permissions.

## [0.2.1] - 2026-09-22

### Added

- `.deb` packaging and CI release on version bump.

## [0.2.0] - 2026-09-22

### Added

- Libadwaita GUI with CLI/UI parity and coverage gate.

[Unreleased]: https://github.com/probityrules/razer-ubuntu/compare/v0.18.1...HEAD
[0.18.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.18.0...v0.18.1
[0.18.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.17.2...v0.18.0
[0.17.2]: https://github.com/probityrules/razer-ubuntu/compare/v0.17.1...v0.17.2
[0.17.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.17.0...v0.17.1
[0.17.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.15.2...v0.16.0
[0.15.2]: https://github.com/probityrules/razer-ubuntu/compare/v0.15.1...v0.15.2
[0.15.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.15.0...v0.15.1
[0.15.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.14.2...v0.15.0
[0.14.2]: https://github.com/probityrules/razer-ubuntu/compare/v0.14.1...v0.14.2
[0.14.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.14.0...v0.14.1
[0.14.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.13.1...v0.14.0
[0.13.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.8.2...v0.9.0
[0.8.2]: https://github.com/probityrules/razer-ubuntu/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.7.5...v0.8.0
[0.7.5]: https://github.com/probityrules/razer-ubuntu/compare/v0.7.4...v0.7.5
[0.7.4]: https://github.com/probityrules/razer-ubuntu/compare/v0.7.3...v0.7.4
[0.7.3]: https://github.com/probityrules/razer-ubuntu/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/probityrules/razer-ubuntu/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/probityrules/razer-ubuntu/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/probityrules/razer-ubuntu/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/probityrules/razer-ubuntu/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/probityrules/razer-ubuntu/releases/tag/v0.2.1
[0.2.0]: https://github.com/probityrules/razer-ubuntu/releases/tag/v0.2.0
