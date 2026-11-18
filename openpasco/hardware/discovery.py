"""Find every sensor source. Blocking (BLE scanning takes seconds): call from a worker thread."""
from openpasco.hardware import pasco_ble, simulated
from openpasco.hardware.base import Sensor


def scan_all() -> tuple[list[Sensor], list[str]]:
    ble, warnings = pasco_ble.scan()
    return simulated.scan() + ble, warnings
