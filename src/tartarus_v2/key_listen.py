"""Live Tartarus key listen helpers (EV_KEY + active profile mapping)."""

from __future__ import annotations

import logging
import select
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from tartarus_v2.input.keys import CODE_TO_LOGICAL, LOGICAL_TO_CODE
from tartarus_v2.profiles import get_active_profile_name, load_profile

log = logging.getLogger("tartarus_v2.key_listen")

UpdateFn = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class KeyLine:
    code: int
    ev_name: str
    logical: str
    layer: str
    mapping: str
    pressed: bool


def ev_key_name(code: int, ecodes: Any | None = None) -> str:
    """Best-effort Linux EV_KEY symbolic name for a keycode."""
    if ecodes is None:
        try:
            from evdev import ecodes as _ecodes

            ecodes = _ecodes
        except ImportError:
            return f"code={code}"
    names = ecodes.KEY.get(code) if hasattr(ecodes, "KEY") else None
    if isinstance(names, (list, tuple)) and names:
        return str(names[0])
    if isinstance(names, str):
        return names
    return f"KEY_{code}"


def format_binding(binding: Any) -> str:
    if binding is None:
        return "(no mapping)"
    if isinstance(binding, str):
        return binding
    if isinstance(binding, dict):
        kind = binding.get("type", "action")
        if kind == "macro":
            steps = binding.get("steps") or []
            taps = []
            for step in steps:
                if isinstance(step, dict) and "tap" in step:
                    taps.append(str(step["tap"]))
            return "macro(" + ",".join(taps) + ")" if taps else "macro"
        if kind == "key":
            return str(binding.get("key") or binding.get("keys") or "key")
        return str(kind)
    return str(binding)


def binding_for_logical(profile: dict[str, Any], logical: str, *, hypershift: bool) -> Any | None:
    layer_name = "hypershift" if hypershift else "standard"
    layer = profile.get(layer_name) or {}
    bindings = layer.get("bindings") or {}
    return bindings.get(logical)


def describe_press(
    code: int,
    *,
    pressed: bool,
    profile: dict[str, Any],
    hypershift_held: bool,
    ecodes: Any | None = None,
) -> KeyLine:
    logical = CODE_TO_LOGICAL.get(code, "?")
    layer = "hypershift" if hypershift_held else "standard"
    mapping = "(unknown logical — update LOGICAL_TO_CODE)"
    if logical != "?":
        hs_key = profile.get("hypershift_key") or "mode"
        if logical == hs_key:
            mapping = f"(hypershift modifier: {hs_key})"
        else:
            mapping = format_binding(binding_for_logical(profile, logical, hypershift=hypershift_held))
    return KeyLine(
        code=code,
        ev_name=ev_key_name(code, ecodes),
        logical=logical,
        layer=layer,
        mapping=mapping,
        pressed=pressed,
    )


def format_key_line(line: KeyLine) -> str:
    state = "DOWN" if line.pressed else "UP"
    return (
        f"{state}  {line.ev_name} ({line.code})  "
        f"logical={line.logical}  layer={line.layer}  → {line.mapping}"
    )


def open_listen_devices(*, prefer: str | None = None) -> tuple[list[Any], str]:
    """Open Tartarus input nodes for listen / highlight (no grab).

    prefer:
      - ``"physical"`` — keypad EV_KEY only
      - ``"virtual"`` — remapper uinput output only
      - ``None`` — follow daemon status (running → virtual, else physical),
        falling back to whichever device exists
    """
    try:
        import evdev
    except ImportError as exc:
        raise RuntimeError("evdev is not installed") from exc

    if prefer is None:
        try:
            from tartarus_v2 import daemon_control

            prefer = "virtual" if daemon_control.status().running else "physical"
        except Exception:  # noqa: BLE001
            prefer = "auto"
    if prefer not in ("physical", "virtual", "auto"):
        prefer = "auto"

    physical: list[Any] = []
    virtual: list[Any] = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
        except OSError:
            continue
        name = d.name or ""
        lower = name.lower()
        if name == "Tartarus V2 Virtual Keyboard":
            virtual.append(d)
        elif "tartarus" in lower and "virtual" not in lower:
            physical.append(d)

    if prefer == "physical":
        if physical:
            return physical, "physical"
        raise RuntimeError(
            "No physical Tartarus EV_KEY devices. Is the keypad plugged in? "
            "If the remap daemon is running, turn it off to read raw EV_KEY."
        )
    if prefer == "virtual":
        if virtual:
            return virtual, "virtual"
        raise RuntimeError(
            "No Tartarus virtual keyboard. Start the remap daemon to listen "
            "to remapped output."
        )

    if physical:
        return physical, "physical"
    if virtual:
        return virtual, "virtual"
    raise RuntimeError(
        "No Tartarus input devices found. Plug in the keypad, or start the "
        "remap daemon to expose the virtual keyboard."
    )


def open_tartarus_devices() -> list[Any]:
    """Open physical Tartarus evdev nodes (no grab). Raises if none / no evdev."""
    devices, mode = open_listen_devices(prefer="physical")
    if mode != "physical":
        raise RuntimeError(
            "No Tartarus evdev devices found. Is the keypad plugged in? "
            "If the daemon is running it may have exclusive grab — stop it and retry."
        )
    return devices


def describe_virtual_press(
    code: int,
    *,
    pressed: bool,
    profile: dict[str, Any],
    hypershift_held: bool,
    ecodes: Any | None = None,
) -> KeyLine:
    """Describe a remapped virtual-keyboard EV_KEY (daemon on)."""
    logicals = logicals_for_output_code(profile, code, hypershift=hypershift_held)
    logical = ",".join(logicals) if logicals else "?"
    layer = "hypershift" if hypershift_held else "standard"
    if logicals:
        mapping = "(virtual keyboard output)"
    else:
        mapping = "(unmatched output — no profile binding emits this key)"
    return KeyLine(
        code=code,
        ev_name=ev_key_name(code, ecodes),
        logical=logical,
        layer=layer,
        mapping=mapping,
        pressed=pressed,
    )


class LiveKeyMonitor:
    """Background evdev listener that reports pressed keys + profile mappings.

    Same device selection as KeyHighlightMonitor: physical EV_KEY when the
    daemon is off, virtual keyboard output when it is on.
    """

    def __init__(self, on_update: UpdateFn, *, history: int = 40) -> None:
        self._on_update = on_update
        self._history = history
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._devices: list[Any] = []
        self._pressed: dict[int, KeyLine] = {}
        self._log: deque[str] = deque(maxlen=history)
        self._hypershift = False
        self._profile: dict[str, Any] = {}
        self._ecodes: Any | None = None
        self._mode = "idle"
        self._prefer: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def mode(self) -> str:
        return self._mode

    def start(self, *, prefer: str | None = None) -> None:
        if self.running:
            return
        self._prefer = prefer
        self._stop.clear()
        self._pressed.clear()
        self._log.clear()
        self._hypershift = False
        self._mode = "idle"
        self._profile = load_profile(get_active_profile_name())
        from evdev import ecodes

        self._ecodes = ecodes
        self._thread = threading.Thread(target=self._run, name="tartarus-key-listen", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        for d in self._devices:
            try:
                d.close()
            except Exception:  # noqa: BLE001
                pass
        self._devices = []
        self._pressed.clear()
        self._mode = "stopped"
        self._emit_status("Stopped")

    def reload_profile(self) -> None:
        try:
            self._profile = load_profile(get_active_profile_name())
            refreshed: dict[int, KeyLine] = {}
            for code, line in self._pressed.items():
                if self._mode == "virtual":
                    refreshed[code] = describe_virtual_press(
                        code,
                        pressed=True,
                        profile=self._profile,
                        hypershift_held=self._hypershift,
                        ecodes=self._ecodes,
                    )
                else:
                    refreshed[code] = describe_press(
                        code,
                        pressed=True,
                        profile=self._profile,
                        hypershift_held=self._hypershift,
                        ecodes=self._ecodes,
                    )
            self._pressed = refreshed
            self._emit_status(f"Profile reloaded: {self._profile.get('name')}")
        except Exception as exc:  # noqa: BLE001
            self._emit_status(f"Profile reload failed: {exc}")

    def _emit_status(self, status: str) -> None:
        self._publish(status=status)

    def _publish(self, *, status: str | None = None) -> None:
        pressed_lines = [format_key_line(self._pressed[c]) for c in sorted(self._pressed)]
        payload = {
            "status": status or "Listening",
            "pressed": pressed_lines,
            "log": list(self._log),
            "hypershift": self._hypershift,
            "profile": self._profile.get("name"),
            "mode": self._mode,
            "running": self.running or not self._stop.is_set(),
        }
        try:
            self._on_update(payload)
        except Exception as exc:  # noqa: BLE001
            log.debug("on_update failed: %s", exc)

    def _run(self) -> None:
        try:
            self._devices, self._mode = open_listen_devices(prefer=self._prefer)
        except Exception as exc:  # noqa: BLE001
            self._mode = "unavailable"
            self._publish(status=f"Unavailable: {exc}")
            return

        source = (
            "physical EV_KEY"
            if self._mode == "physical"
            else "virtual keyboard (remapped output)"
        )
        self._emit_status(
            f"Listening ({source}) on "
            + ", ".join(f"{d.path} ({d.name})" for d in self._devices)
            + f" — profile={self._profile.get('name')}"
        )
        fds = {d.fd: d for d in self._devices}
        try:
            while not self._stop.is_set():
                r, _, _ = select.select(list(fds), [], [], 0.25)
                for fd in r:
                    try:
                        events = list(fds[fd].read())
                    except OSError as exc:
                        self._log.appendleft(f"device read error: {exc}")
                        self._publish(status=f"Read error: {exc}")
                        continue
                    for event in events:
                        self._handle_event(event)
        finally:
            self._mode = "stopped"
            self._publish(status="Stopped")

    def _handle_event(self, event: Any) -> None:
        ecodes = self._ecodes
        if ecodes is None:
            return
        if event.type == ecodes.EV_KEY:
            if event.value == 2:  # repeat
                return
            pressed = event.value == 1
            code = int(event.code)

            if self._mode == "virtual":
                hs_code = LOGICAL_TO_CODE.get(self._profile.get("hypershift_key") or "mode")
                if hs_code is not None and code == hs_code:
                    self._hypershift = pressed
                line = describe_virtual_press(
                    code,
                    pressed=pressed,
                    profile=self._profile,
                    hypershift_held=self._hypershift,
                    ecodes=ecodes,
                )
            else:
                logical = CODE_TO_LOGICAL.get(code)
                hs_key = self._profile.get("hypershift_key") or "mode"
                if logical == hs_key:
                    self._hypershift = pressed
                line = describe_press(
                    code,
                    pressed=pressed,
                    profile=self._profile,
                    hypershift_held=self._hypershift,
                    ecodes=ecodes,
                )

            text = format_key_line(line)
            self._log.appendleft(text)
            if pressed:
                self._pressed[code] = line
            else:
                self._pressed.pop(code, None)
            self._publish()
            return

        if self._mode != "physical":
            return
        if event.type == ecodes.EV_REL and event.code == ecodes.REL_WHEEL:
            logical = "scroll_up" if event.value > 0 else "scroll_down" if event.value < 0 else None
            if not logical:
                return
            mapping = format_binding(
                binding_for_logical(self._profile, logical, hypershift=self._hypershift)
            )
            layer = "hypershift" if self._hypershift else "standard"
            text = (
                f"WHEEL  REL_WHEEL ({event.code}) value={event.value}  "
                f"logical={logical}  layer={layer}  → {mapping}"
            )
            self._log.appendleft(text)
            self._publish()


def hypershift_keycode(profile: dict[str, Any] | None = None) -> int | None:
    data = profile or {}
    logical = data.get("hypershift_key") or "mode"
    return LOGICAL_TO_CODE.get(logical)


def _resolve_binding_codes(binding: Any) -> list[int]:
    """Best-effort keycodes a binding would emit (string / key dict only)."""
    if binding is None:
        return []
    try:
        from evdev import ecodes
    except ImportError:
        return []

    from tartarus_v2.input.keys import OUTPUT_ALIASES

    def one(token: str) -> list[int]:
        name = token.strip()
        if not name:
            return []
        if "+" in name and not name.startswith("KEY_"):
            out: list[int] = []
            for part in name.split("+"):
                out.extend(one(part))
            return out
        lower = name.lower()
        if lower in OUTPUT_ALIASES:
            name = OUTPUT_ALIASES[lower]
        if not name.startswith("KEY_") and not name.startswith("BTN_"):
            if len(name) == 1 and name.isalnum():
                name = f"KEY_{name.upper()}"
            else:
                name = f"KEY_{name.upper()}"
        code = getattr(ecodes, name, None)
        return [int(code)] if code is not None else []

    if isinstance(binding, str):
        return one(binding)
    if isinstance(binding, dict) and binding.get("type", "key") == "key":
        raw = binding.get("keys") or binding.get("key") or ""
        if isinstance(raw, list):
            out: list[int] = []
            for item in raw:
                out.extend(one(str(item)))
            return out
        return one(str(raw))
    return []


def logicals_for_output_code(profile: dict[str, Any], code: int, *, hypershift: bool) -> list[str]:
    """Which logical keys map to this output code on the current layer."""
    layer_name = "hypershift" if hypershift else "standard"
    bindings = ((profile.get(layer_name) or {}).get("bindings")) or {}
    hits: list[str] = []
    for logical, binding in bindings.items():
        if code in _resolve_binding_codes(binding):
            hits.append(str(logical))
    if not hits:
        passthrough = CODE_TO_LOGICAL.get(code)
        if passthrough and passthrough not in bindings:
            hits.append(passthrough)
    return hits


class KeyHighlightMonitor:
    """Lightweight press highlighter for the Bindings keymap.

    Daemon off → Tartarus EV_KEY (physical). Daemon on → virtual keyboard output
    reversed through the active profile map when possible.
    """

    def __init__(self, on_update: Callable[[set[str], str], None]) -> None:
        self._on_update = on_update
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._devices: list[Any] = []
        self._pressed: set[str] = set()
        self._profile: dict[str, Any] = {}
        self._mode = "idle"
        self._hypershift = False
        self._ecodes: Any | None = None
        self._prefer: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_profile(self, profile: dict[str, Any]) -> None:
        self._profile = dict(profile or {})

    def start(self, *, prefer: str | None = None) -> None:
        if self.running:
            return
        self._prefer = prefer
        self._stop.clear()
        self._pressed.clear()
        self._hypershift = False
        if not self._profile:
            try:
                self._profile = load_profile(get_active_profile_name())
            except Exception:  # noqa: BLE001
                self._profile = {}
        self._thread = threading.Thread(
            target=self._run, name="tartarus-key-highlight", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        for d in self._devices:
            try:
                d.close()
            except Exception:  # noqa: BLE001
                pass
        self._devices = []
        self._pressed.clear()
        self._publish("stopped")

    def _publish(self, mode: str | None = None) -> None:
        if mode is not None:
            self._mode = mode
        try:
            self._on_update(set(self._pressed), self._mode)
        except Exception as exc:  # noqa: BLE001
            log.debug("highlight on_update failed: %s", exc)

    def _run(self) -> None:
        try:
            from evdev import ecodes

            self._ecodes = ecodes
            self._devices, mode = open_listen_devices(prefer=self._prefer)
        except Exception as exc:  # noqa: BLE001
            self._publish(f"unavailable: {exc}")
            return
        self._publish(mode)
        fds = {d.fd: d for d in self._devices}
        try:
            while not self._stop.is_set():
                r, _, _ = select.select(list(fds), [], [], 0.25)
                for fd in r:
                    try:
                        events = list(fds[fd].read())
                    except OSError:
                        continue
                    for event in events:
                        self._handle(event, mode)
        finally:
            self._publish("stopped")

    def _handle(self, event: Any, mode: str) -> None:
        ecodes = self._ecodes
        if ecodes is None:
            return
        if event.type != ecodes.EV_KEY or event.value == 2:
            return
        pressed = event.value == 1
        code = int(event.code)
        logicals: list[str] = []

        if mode == "physical":
            logical = CODE_TO_LOGICAL.get(code)
            if logical:
                hs_key = self._profile.get("hypershift_key") or "mode"
                if logical == hs_key:
                    self._hypershift = pressed
                logicals = [logical]
        else:
            logicals = logicals_for_output_code(
                self._profile, code, hypershift=self._hypershift
            )
            # Also treat hypershift modifier if the virtual device emits it.
            hs_code = LOGICAL_TO_CODE.get(self._profile.get("hypershift_key") or "mode")
            if hs_code is not None and code == hs_code:
                self._hypershift = pressed

        if not logicals:
            return
        for logical in logicals:
            if pressed:
                self._pressed.add(logical)
            else:
                self._pressed.discard(logical)
        self._publish(mode)
