"""HID package for Tartarus V2."""

from tartarus_v2.hid.device import DeviceError, TartarusDevice
from tartarus_v2.hid.chroma import ChromaController

__all__ = ["DeviceError", "TartarusDevice", "ChromaController"]
