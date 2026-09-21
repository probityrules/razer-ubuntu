"""evdev → uinput remapper with Hypershift layer support."""

from __future__ import annotations

import logging
import select
import time
from pathlib import Path
from typing import Any

from tartarus_v2.input import keys as keytable
from tartarus_v2.input.macros import play_macro

log = logging.getLogger("tartarus_v2.remap")


class Remapper:
    def __init__(
        self,
        profile: dict[str, Any],
        debug: bool = False,
        on_profile_switch: Any | None = None,
    ) -> None:
        self.profile = profile
        self.debug = debug
        self.on_profile_switch = on_profile_switch
        self._hypershift_held = False
        self._devices: list[Any] = []
        self._ui: Any = None
        self._ecodes: Any = None
        self._running = False

    def _require_evdev(self) -> Any:
        try:
            import evdev
            from evdev import ecodes
        except ImportError as exc:
            raise RuntimeError(
                "evdev is required on Linux. Install with: pip install 'tartarus-v2[linux]'"
            ) from exc
        self._ecodes = ecodes
        return evdev

    def resolve_key_token(self, token: Any) -> list[int]:
        """Resolve a binding token into one or more Linux keycodes."""
        ecodes = self._ecodes
        if isinstance(token, int):
            return [token]
        if isinstance(token, list):
            out: list[int] = []
            for t in token:
                out.extend(self.resolve_key_token(t))
            return out
        if not isinstance(token, str):
            raise ValueError(f"Invalid key token: {token!r}")

        name = token.strip()
        if "+" in name and not name.startswith("KEY_"):
            parts = [p.strip() for p in name.split("+") if p.strip()]
            out = []
            for p in parts:
                out.extend(self.resolve_key_token(p))
            return out

        lower = name.lower()
        if lower in keytable.OUTPUT_ALIASES:
            name = keytable.OUTPUT_ALIASES[lower]
        if not name.startswith("KEY_") and not name.startswith("BTN_"):
            # single letter / digit
            if len(name) == 1 and name.isalnum():
                name = f"KEY_{name.upper()}"
            else:
                name = f"KEY_{name.upper()}"

        code = getattr(ecodes, name, None)
        if code is None:
            raise ValueError(f"Unknown key name: {token!r} (resolved {name})")
        return [int(code)]

    def find_devices(self) -> list[Any]:
        evdev = self._require_evdev()
        found = []
        by_id = Path("/dev/input/by-id")
        candidates: list[Path] = []
        if by_id.is_dir():
            for p in sorted(by_id.iterdir()):
                name = p.name.lower()
                if "tartarus" in name and ("event-kbd" in name or "event-mouse" in name):
                    candidates.append(p)
        if not candidates:
            for path in evdev.list_devices():
                try:
                    dev = evdev.InputDevice(path)
                except OSError:
                    continue
                if "tartarus" in (dev.name or "").lower():
                    found.append(dev)
            return found

        for link in candidates:
            try:
                found.append(evdev.InputDevice(str(link.resolve())))
            except OSError as exc:
                log.warning("Could not open %s: %s", link, exc)
        return found

    def start(self) -> None:
        evdev = self._require_evdev()
        from evdev import UInput, ecodes

        devices = self.find_devices()
        if not devices:
            raise RuntimeError(
                "No Tartarus V2 input devices found under /dev/input. "
                "Check permissions (input group) and that the keypad is plugged in."
            )

        caps: dict[int, list[int]] = {ecodes.EV_KEY: [], ecodes.EV_REL: []}
        key_set: set[int] = set()
        for code in range(ecodes.KEY_MAX):
            key_set.add(code)
        caps[ecodes.EV_KEY] = sorted(key_set)
        caps[ecodes.EV_REL] = [ecodes.REL_WHEEL, ecodes.REL_HWHEEL]

        self._ui = UInput(caps, name="Tartarus V2 Virtual Keyboard", version=0x1)
        self._devices = devices
        for d in self._devices:
            try:
                d.grab()
                log.info("Grabbed %s (%s)", d.name, d.path)
            except OSError as exc:
                log.error("Failed to grab %s: %s", d.path, exc)
                raise

        self._running = True
        log.info(
            "Remapper started; hypershift_key=%r",
            self.profile.get("hypershift_key"),
        )

    def stop(self) -> None:
        self._running = False
        for d in self._devices:
            try:
                d.ungrab()
            except Exception:  # noqa: BLE001
                pass
            try:
                d.close()
            except Exception:  # noqa: BLE001
                pass
        self._devices = []
        if self._ui is not None:
            try:
                self._ui.close()
            except Exception:  # noqa: BLE001
                pass
            self._ui = None

    def _emit(self, codes: list[int], pressed: bool) -> None:
        from evdev import ecodes

        assert self._ui is not None
        value = 1 if pressed else 0
        for code in codes:
            self._ui.write(ecodes.EV_KEY, code, value)
        self._ui.syn()

    def _logical_from_event(self, event: Any) -> str | None:
        from evdev import ecodes

        if event.type == ecodes.EV_KEY:
            if event.code in keytable.CODE_TO_LOGICAL:
                return keytable.CODE_TO_LOGICAL[event.code]
            return None
        if event.type == ecodes.EV_REL and event.code == ecodes.REL_WHEEL:
            if event.value > 0:
                return "scroll_up"
            if event.value < 0:
                return "scroll_down"
        return None

    def _binding_for(self, logical: str) -> Any | None:
        layer_name = "hypershift" if self._hypershift_held else "standard"
        layer = self.profile.get(layer_name) or {}
        bindings = layer.get("bindings") or {}
        return bindings.get(logical)

    def _apply_binding(self, binding: Any, pressed: bool) -> None:
        if binding is None:
            return
        if isinstance(binding, dict):
            kind = binding.get("type", "key")
            if kind == "hypershift":
                # Should not appear as output binding; handled separately
                return
            if kind == "profile_next" and pressed:
                if self.on_profile_switch:
                    self.on_profile_switch("next")
                return
            if kind == "profile_prev" and pressed:
                if self.on_profile_switch:
                    self.on_profile_switch("prev")
                return
            if kind == "macro" and pressed:
                steps = binding.get("steps") or []
                play_macro(steps, self._emit, self.resolve_key_token)
                return
            if kind == "key":
                codes = self.resolve_key_token(binding.get("keys") or binding.get("key"))
                self._emit(codes, pressed)
                return
            log.warning("Unknown binding type %r", kind)
            return

        # string / list shorthand
        if pressed:
            codes = self.resolve_key_token(binding)
            self._emit(codes, True)
            time.sleep(0.01)
            self._emit(list(reversed(codes)), False)
        # for hold-style we need press/release; shorthand taps on press only

    def _handle_key(self, logical: str, pressed: bool) -> None:
        hs_key = self.profile.get("hypershift_key")
        if logical == hs_key:
            was = self._hypershift_held
            self._hypershift_held = pressed
            if was != pressed:
                log.info("Hypershift %s", "ENTER" if pressed else "EXIT")
            return

        binding = self._binding_for(logical)
        if binding is None:
            # passthrough default physical code if known
            code = keytable.LOGICAL_TO_CODE.get(logical)
            if code is not None:
                self._emit([code], pressed)
            elif self.debug:
                log.debug("No binding for %s pressed=%s", logical, pressed)
            return

        if self.debug:
            layer = "hypershift" if self._hypershift_held else "standard"
            log.debug("layer=%s key=%s pressed=%s binding=%r", layer, logical, pressed, binding)

        # For string bindings, support hold (press/release) when single key
        if isinstance(binding, str) and "+" not in binding:
            try:
                codes = self.resolve_key_token(binding)
                self._emit(codes, pressed)
                return
            except ValueError:
                pass

        if isinstance(binding, dict) and binding.get("type", "key") == "key":
            codes = self.resolve_key_token(binding.get("keys") or binding.get("key"))
            self._emit(codes, pressed)
            return

        # macros / combos / profile actions fire on press
        if pressed:
            self._apply_binding(binding, True)

    def run_forever(self) -> None:
        if not self._devices:
            self.start()
        assert self._ui is not None
        fds = {d.fd: d for d in self._devices}
        try:
            while self._running:
                r, _, _ = select.select(list(fds.keys()), [], [], 0.5)
                for fd in r:
                    dev = fds[fd]
                    for event in dev.read():
                        logical = self._logical_from_event(event)
                        if logical is None:
                            continue
                        from evdev import ecodes

                        if event.type == ecodes.EV_KEY:
                            if event.value == 2:  # hold repeat
                                continue
                            self._handle_key(logical, event.value == 1)
                        elif event.type == ecodes.EV_REL:
                            # scroll: synthesize press
                            self._handle_key(logical, True)
        finally:
            self.stop()
