"""Real, local environmental sensors. See CONTRACT.md SS38.

Deliberately scoped to signals that need no camera/microphone (those
are already `avishkar_layla.voice`/`vision`, Directive D Parts I/II,
with their own consent discipline) -- idle time, power/battery state,
system load, and real network reachability. Every sensor here reads
genuine local OS/process state; none returns a fabricated value, and
each raises `SensorUnavailableError` rather than a fake reading when
its real backing data source doesn't exist on this machine (e.g. no
battery on a desktop).
"""

from __future__ import annotations

import dataclasses
import datetime
import platform
import socket
import time
from typing import Any, Mapping

from .errors import SensorUnavailableError


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclasses.dataclass(frozen=True)
class SensorReading:
    sensor_id: str
    sensor_type: str
    value: Any
    unit: str
    timestamp: str = dataclasses.field(default_factory=_now)
    confidence: float = 1.0
    metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)


class Sensor:
    sensor_id: str
    sensor_type: str

    def read(self) -> SensorReading:
        raise NotImplementedError


class IdleTimeSensor(Sensor):
    """Real seconds-since-last-input, via the real Win32
    `GetLastInputInfo` API. A genuine, non-invasive presence proxy --
    reads only a timestamp, never keystrokes/content. Raises
    SensorUnavailableError on non-Windows platforms rather than
    fabricating an idle time.
    """

    sensor_type = "idle_time"

    def __init__(self, *, sensor_id: str = "idle_time") -> None:
        self.sensor_id = sensor_id

    def read(self) -> SensorReading:
        if platform.system() != "Windows":
            raise SensorUnavailableError("IdleTimeSensor requires Windows (GetLastInputInfo) -- not available on this platform")

        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        try:
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                raise SensorUnavailableError("GetLastInputInfo call failed")
            idle_ms = ctypes.windll.kernel32.GetTickCount() - info.dwTime
        except SensorUnavailableError:
            raise
        except Exception as exc:
            raise SensorUnavailableError(f"IdleTimeSensor read failed: {exc}") from exc

        return SensorReading(sensor_id=self.sensor_id, sensor_type=self.sensor_type, value=idle_ms / 1000.0, unit="seconds")


class BatterySensor(Sensor):
    """Real battery percentage and power-source state via `psutil`.
    Raises SensorUnavailableError on a machine with no battery (most
    desktops) rather than fabricating a percentage.
    """

    sensor_type = "battery"

    def __init__(self, *, sensor_id: str = "battery") -> None:
        self.sensor_id = sensor_id

    def read(self) -> SensorReading:
        import psutil

        battery = psutil.sensors_battery()
        if battery is None:
            raise SensorUnavailableError("no battery sensor is available on this machine")
        return SensorReading(
            sensor_id=self.sensor_id, sensor_type=self.sensor_type, value=float(battery.percent), unit="percent",
            metadata={"power_plugged": bool(battery.power_plugged)},
        )


class SystemLoadSensor(Sensor):
    """Real CPU/memory load via `psutil`. A genuine "is this device
    under heavy use right now" signal.
    """

    sensor_type = "system_load"

    def __init__(self, *, sensor_id: str = "system_load", cpu_sample_seconds: float = 0.1) -> None:
        self.sensor_id = sensor_id
        self._cpu_sample_seconds = cpu_sample_seconds

    def read(self) -> SensorReading:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=self._cpu_sample_seconds)
        memory_percent = psutil.virtual_memory().percent
        return SensorReading(
            sensor_id=self.sensor_id, sensor_type=self.sensor_type, value=float(cpu_percent), unit="percent",
            metadata={"memory_percent": float(memory_percent)},
        )


class NetworkConnectivitySensor(Sensor):
    """A REAL reachability check -- attempts a genuine TCP connection
    to a well-known, stable public endpoint (default: 8.8.8.8:53).
    Deliberately stronger than checking "is a network interface up"
    (which can be true with no actual internet path); this is a real
    socket-level probe with a short timeout, same discipline as this
    session's channel-transport rejection tests.
    """

    sensor_type = "network_connectivity"

    def __init__(
        self, *, sensor_id: str = "network_connectivity", host: str = "8.8.8.8", port: int = 53,
        timeout_seconds: float = 2.0, clock=time.monotonic,
    ) -> None:
        self.sensor_id = sensor_id
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._clock = clock

    def read(self) -> SensorReading:
        start = self._clock()
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout_seconds):
                reachable = True
        except OSError:
            reachable = False
        latency_ms = (self._clock() - start) * 1000
        return SensorReading(
            sensor_id=self.sensor_id, sensor_type=self.sensor_type, value=reachable, unit="boolean",
            metadata={"probe_target": f"{self._host}:{self._port}", "latency_ms": latency_ms},
        )
