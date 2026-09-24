"""evdev → uinput remapper with Hypershift layer support."""

from __future__ import annotations

import errno
import logging
import os
import select
import time
from pathlib import Path
from typing import Any

from tartarus_v2.input import keys as keytable
from tartarus_v2.input.macros import play_macro

log = logging.getLogger("tartarus_v2.remap")


def is_tartarus_event_node(name: str) -> bool:
    """True for physical Tartarus evdev by-id links, including ``*-event-if01``.

    The keypad can emit key events on a node that is not named ``event-kbd``
    or ``event-mouse``. Leaving that node ungrabbed lets firmware default
    keys through to text editors while the daemon looks like it is running.
    """
    lower = name.lower()
    if "tartarus" not in lower:
        return False
    if "virtual" in lower or "hidraw" in lower:
        return False
    return "event" in lower


def grab_error_is_fatal(exc: OSError) -> bool:
    """Stale nodes disappear after chroma detaches a kernel driver; skip those."""
    err = getattr(exc, "errno", None)
    return err not in (errno.ENODEV, errno.ENOENT, errno.ENXIO)


def input_node_lost_message(exc: BaseException) -> str:
    """Explain a mid-run ENODEV so it is not mistaken for a /dev/uinput failure.

    The keypad's boot-keyboard evdev node vanishes when another process detaches
    that USB interface. The remapper was the only path turning those events into
    keystrokes, so text editors then receive nothing — not even firmware defaults.
    """
    return (
        f"Keypad input node disappeared ({exc}). Another program detached the "
        "keyboard USB interface while the remap daemon was reading it, so text "
        "editors receive no keys, including firmware defaults. Replug the "
        "Tartarus if keys stay dead after the daemon stops."
    )


def uinput_failure_message(exc: OSError) -> str:
    err = getattr(exc, "errno", None)
    if err in (errno.EACCES, errno.EPERM):
        return (
            "Cannot create the virtual keyboard (/dev/uinput): permission denied. "
            "The keypad keeps sending its default keys to text editors until this works. "
            "Root is not required. Run tartarus-v2 fix-permissions, then log out and back in "
            "so this session can write /dev/uinput (input group or the tartarus udev rule)."
        )
    if err in (errno.ENOENT, errno.ENODEV) or not os.path.exists("/dev/uinput"):
        return (
            "Cannot create the virtual keyboard because /dev/uinput is missing. "
            "Load it with: sudo modprobe uinput   or run tartarus-v2 fix-permissions. "
            "Root is not required to run the remap daemon after that node exists and is writable."
        )
    return (
        f"Failed to create the virtual keyboard (/dev/uinput): {exc}. "
        "Remapped keys will not reach other apps. Root is not required; "
        "run tartarus-v2 fix-permissions and log out/in."
    )


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
                if is_tartarus_event_node(p.name):
                    candidates.append(p)

        for link in candidates:
            try:
                dev = evdev.InputDevice(str(link.resolve()))
            except OSError as exc:
                log.warning("Could not open %s: %s", link, exc)
                continue
            if not self._is_physical_tartarus(dev):
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
                continue
            found.append(dev)
        if found:
            return found

        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            # Never remap our own uinput device — only the physical keypad.
            if self._is_physical_tartarus(dev):
                found.append(dev)
            else:
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
        return found

    @staticmethod
    def _is_physical_tartarus(dev: Any) -> bool:
        name = (getattr(dev, "name", None) or "").strip()
        lower = name.lower()
        if "tartarus" not in lower:
            return False
        if "virtual" in lower:
            return False
        if name == "Tartarus V2 Virtual Keyboard":
            return False
        return True

    def start(self) -> None:
        evdev = self._require_evdev()
        from evdev import UInput, ecodes

        devices = self.find_devices()
        if not devices:
            raise RuntimeError(
                "No Tartarus V2 input devices found under /dev/input. "
                "Check permissions (input group) and that the keypad is plugged in."
            )
        log.info(
            "Tartarus event nodes: %s",
            ", ".join(f"{getattr(d, 'name', '?')} ({getattr(d, 'path', '?')})" for d in devices),
        )

        caps: dict[int, list[int]] = {ecodes.EV_KEY: [], ecodes.EV_REL: []}
        key_set: set[int] = set()
        for code in range(ecodes.KEY_MAX):
            key_set.add(code)
        caps[ecodes.EV_KEY] = sorted(key_set)
        caps[ecodes.EV_REL] = [ecodes.REL_WHEEL, ecodes.REL_HWHEEL]

        try:
            log.info("Creating virtual keyboard via /dev/uinput")
            self._ui = UInput(caps, name="Tartarus V2 Virtual Keyboard", version=0x1)
        except OSError as exc:
            for dev in devices:
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
            raise RuntimeError(uinput_failure_message(exc)) from exc
        self._devices = devices
        grabbed = 0
        kept: list[Any] = []
        for d in list(self._devices):
            try:
                d.grab()
            except OSError as exc:
                if not grab_error_is_fatal(exc):
                    log.warning("Skipping %s (%s); node went away: %s", d.path, d.name, exc)
                    try:
                        d.close()
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                log.error("Failed to grab %s: %s", d.path, exc)
                # Without exclusive grab, stock HID still reaches apps (looks like
                # "in-game only" remaps). Fail hard so the daemon does not pretend
                # to be remapping system-wide.
                self.stop()
                raise RuntimeError(
                    f"Could not exclusive-grab {d.path} ({d.name}): {exc}. "
                    "Remapping cannot be system-wide without grab. "
                    "Run: tartarus-v2 fix-permissions  (then log out/in), "
                    "and ensure no other process has the device open. "
                    "Root is not required."
                ) from exc
            grabbed += 1
            kept.append(d)
            log.info("Grabbed %s (%s) — system-wide remap active for this node", d.name, d.path)
        self._devices = kept

        if grabbed == 0:
            self.stop()
            raise RuntimeError("No Tartarus devices were grabbed; remapper aborted.")

        self._running = True
        log.info(
            "Remapper started (system-wide uinput); hypershift_key=%r devices=%d",
            self.profile.get("hypershift_key"),
            grabbed,
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
        return keytable.lookup_binding(bindings, logical)

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
        hs_key = keytable.canonical_logical(str(self.profile.get("hypershift_key") or ""))
        if keytable.canonical_logical(logical) == hs_key:
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
                try:
                    r, _, _ = select.select(list(fds.keys()), [], [], 0.5)
                except OSError as exc:
                    if grab_error_is_fatal(exc):
                        raise
                    raise RuntimeError(input_node_lost_message(exc)) from exc
                for fd in r:
                    dev = fds[fd]
                    try:
                        events = list(dev.read())
                    except OSError as exc:
                        if grab_error_is_fatal(exc):
                            raise
                        log.error(
                            "Tartarus input node %s disappeared: %s",
                            getattr(dev, "path", fd),
                            exc,
                        )
                        raise RuntimeError(input_node_lost_message(exc)) from exc
                    for event in events:
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
