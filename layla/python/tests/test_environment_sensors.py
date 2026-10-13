"""Real environmental sensor tests -- every sensor here reads genuine
local OS/process state on this machine (idle time via the real Win32
API, real battery via psutil -- this machine genuinely has one, real
CPU/memory load, and a real socket-level network reachability probe).
None of this records audio/video or touches the visible desktop, so
it's safe and appropriate to exercise for real, automatically.
"""

import platform
import unittest

from avishkar_layla.environment.errors import SensorUnavailableError
from avishkar_layla.environment.sensors import BatterySensor, IdleTimeSensor, NetworkConnectivitySensor, SystemLoadSensor


class TestIdleTimeSensorReal(unittest.TestCase):
    @unittest.skipUnless(platform.system() == "Windows", "IdleTimeSensor is Windows-only by design")
    def test_real_idle_time_is_a_non_negative_number_of_seconds(self):
        reading = IdleTimeSensor().read()
        self.assertEqual(reading.sensor_type, "idle_time")
        self.assertEqual(reading.unit, "seconds")
        self.assertGreaterEqual(reading.value, 0.0)


class TestBatterySensorReal(unittest.TestCase):
    def test_reports_real_state_or_raises_when_genuinely_unavailable(self):
        try:
            reading = BatterySensor().read()
        except SensorUnavailableError:
            self.skipTest("no battery on this machine")
            return
        self.assertEqual(reading.sensor_type, "battery")
        self.assertGreaterEqual(reading.value, 0.0)
        self.assertLessEqual(reading.value, 100.0)
        self.assertIn("power_plugged", reading.metadata)


class TestSystemLoadSensorReal(unittest.TestCase):
    def test_real_cpu_and_memory_percent_are_in_range(self):
        reading = SystemLoadSensor(cpu_sample_seconds=0.05).read()
        self.assertEqual(reading.sensor_type, "system_load")
        self.assertGreaterEqual(reading.value, 0.0)
        self.assertLessEqual(reading.value, 100.0)
        self.assertGreaterEqual(reading.metadata["memory_percent"], 0.0)


class TestNetworkConnectivitySensorReal(unittest.TestCase):
    def test_real_reachable_host_reports_true(self):
        sensor = NetworkConnectivitySensor(host="8.8.8.8", port=53, timeout_seconds=3.0)
        reading = sensor.read()
        if reading.value is False:
            self.skipTest("no outbound network access in this environment")
        self.assertTrue(reading.value)
        self.assertEqual(reading.sensor_type, "network_connectivity")
        self.assertIn("latency_ms", reading.metadata)

    def test_unreachable_host_reports_false_not_an_exception(self):
        # A real, valid but non-routable address (TEST-NET-1, RFC 5737) --
        # the probe genuinely attempts and genuinely times out.
        sensor = NetworkConnectivitySensor(host="192.0.2.1", port=81, timeout_seconds=1.0)
        reading = sensor.read()
        self.assertFalse(reading.value)


if __name__ == "__main__":
    unittest.main()
